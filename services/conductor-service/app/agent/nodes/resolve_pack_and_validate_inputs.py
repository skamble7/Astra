from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from jsonschema import Draft202012Validator, ValidationError

from app.clients.capability_service import CapabilityServiceClient

logger = logging.getLogger("app.agent.nodes.resolve")


def _pick_playbook(resolved_pack: Dict[str, Any], requested_id: str | None) -> Dict[str, Any] | None:
    """
    Pick a playbook dict from the resolved pack. Prefer requested_id; else first item.
    Expected shape (examples):
      { "playbooks": [ { "id": "...", "steps": [...] }, ... ] }
    """
    playbooks: List[Dict[str, Any]] = (resolved_pack or {}).get("playbooks") or []
    if not playbooks:
        return None
    if requested_id:
        for pb in playbooks:
            if pb.get("id") == requested_id:
                return pb
    # fallback to first
    return playbooks[0]


def _extract_pack_input_id(resolved_pack: Dict[str, Any]) -> Optional[str]:
    """
    Try common locations for pack_input_id in capability-service responses.
    """
    if "pack_input_id" in resolved_pack:
        return resolved_pack["pack_input_id"]
    pack_meta = resolved_pack.get("pack") or {}
    if "pack_input_id" in pack_meta:
        return pack_meta["pack_input_id"]
    return None


def _validate_inputs_against_schema(user_inputs: Dict[str, Any], schema_doc: Dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Validate StartRunRequest.inputs against the pack_input.json_schema.
    Your schema expects a top-level object with an `inputs` property.
    Some packs ship a UI schema (no 'inputs'); we skip strict validation in that case.
    """
    errors: list[str] = []
    try:
        schema = schema_doc.get("json_schema") or {}
        schema_id = schema.get("$id") or schema.get("$schema") or "<unknown-schema>"
        # Only validate if the schema clearly models { inputs: {...} }
        props = (schema.get("properties") or {})
        if "inputs" not in props:
            logger.warning(
                "Pack-input schema appears to be a UI form (no top-level 'inputs'); skipping strict validation. schema_id=%s",
                schema.get("$id") or schema.get("$schema") or "(missing)",
            )
            return False, []

        validator = Draft202012Validator(schema)
        for err in sorted(validator.iter_errors({"inputs": user_inputs}), key=str):
            errors.append(f"{err.message} at path: {'/'.join(map(str, err.path))}")
        ok = len(errors) == 0
        return ok, errors
    except ValidationError as ve:
        return False, [str(ve)]
    except Exception as e:
        logger.warning("Input validation encountered an error; continuing permissively: %s", e)
        return False, []


async def resolve_pack_and_validate_inputs(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    - Fetch resolved pack (capabilities & playbooks)
    - Pick the playbook (by id or first)
    - Fetch pack-input document; validate provided inputs if schema matches our contract
    - Populate state.pack (capabilities_by_id, playbook, pack_input_id), and state.inputs.validation
    """
    req = state["request"]
    pack_id: str = req["pack_id"]
    requested_playbook_id: Optional[str] = req.get("playbook_id")

    caps = CapabilityServiceClient()

    # 1) Resolve pack (capabilities & playbooks)
    resolved = await caps.get_pack_resolved(pack_id)

    # 2) Build index for capabilities by id
    caps_list: List[Dict[str, Any]] = resolved.get("capabilities") or []
    capabilities_by_id = {c.get("id"): c for c in caps_list if c.get("id")}

    # 3) Choose playbook (never None if there is at least one)
    playbook = _pick_playbook(resolved, requested_playbook_id)
    if not playbook:
        # Hard fail: we cannot proceed without a playbook
        raise RuntimeError(f"No playbooks found in pack '{pack_id}'")

    # 4) Pack input & validation
    pack_input_id = _extract_pack_input_id(resolved)
    pack_input_doc: Dict[str, Any] = {}
    validated = False
    val_errors: list[str] = []
    if pack_input_id:
        pack_input_doc = await caps.get_pack_input(pack_input_id)
        validated, val_errors = _validate_inputs_against_schema(state["inputs"]["raw"], pack_input_doc)
    else:
        logger.warning("Resolved pack '%s' did not expose a pack_input_id; skipping strict validation.", pack_id)

    state["pack"] = {
        "resolved": resolved,
        "pack_input_id": pack_input_id,
        "capabilities_by_id": capabilities_by_id,
        "playbook": playbook,
    }
    state["inputs"]["validation"] = {"ok": validated if validated else (len(val_errors) == 0), "errors": val_errors}

    logger.info(
        "Pack resolved and inputs prepared (pack_input_id=%s, schema_id=%s, validated=%s)",
        pack_input_id or "(none)",
        (pack_input_doc.get("json_schema") or {}).get("$id") or (pack_input_doc.get("json_schema") or {}).get("$schema") or "(unknown)",
        validated,
    )
    return state