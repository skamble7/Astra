# services/conductor-service/app/agent/nodes/resolve_pack_and_validate_inputs.py
from __future__ import annotations

import logging
from typing import Any, Dict

from jsonschema import Draft202012Validator, ValidationError

from app.clients.capability_service import CapabilityServiceClient
from app.clients.artifact_service import ArtifactServiceClient  # used later to check baseline existence

logger = logging.getLogger("app.agent.nodes.resolve")


async def resolve_pack_and_validate_inputs(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resolve pack via capability-service and validate request inputs against its Pack Input schema.
    Decide strategy (baseline|delta): baseline if workspace has no parent in artifact-service.
    """
    cap_client = CapabilityServiceClient()
    art_client = ArtifactServiceClient()

    pack_id = state["run"]["pack_id"]
    resolved = await cap_client.get_pack_resolved(pack_id)

    pack_input_id = resolved.get("pack_input_id")
    pack_input = None
    if pack_input_id:
        pack_input = await cap_client.get_pack_input(pack_input_id)
        schema = pack_input.get("json_schema") or {}
        # We validate the WHOLE request body shape fragment expects {"inputs": {...}} or as declared.
        # Our API already provided a bare inputs object; wrap into {"inputs": inputs} if schema expects it.
        inputs_payload = {"inputs": state["inputs"]["raw"]} if "inputs" in (schema.get("properties") or {}) else state["inputs"]["raw"]

        try:
            Draft202012Validator(schema).validate(inputs_payload)
            state["inputs"]["validation"]["ok"] = True
        except ValidationError as e:
            state["inputs"]["validation"]["ok"] = False
            state["inputs"]["validation"]["errors"].append(str(e))
            raise

    # figure out baseline vs delta: if no workspace parent -> baseline else delta
    workspace_id = state["run"]["workspace_id"]
    try:
        await art_client.get_workspace_parent(workspace_id)
        strategy = "delta"
    except Exception:
        strategy = "baseline"

    state["run"]["strategy"] = strategy
    state["pack"] = {
        "resolved": resolved,
        "pack_input_id": pack_input_id,
        "pack_input": pack_input,
        "capabilities_by_id": {c["id"]: c for c in resolved.get("capabilities", [])},
    }

    # Select playbook by id from resolved
    playbook_id = state["run"]["playbook_id"]
    pbs = resolved.get("playbooks", []) or []
    selected = next((pb for pb in pbs if pb.get("id") == playbook_id), None)
    if selected is None:
        raise RuntimeError(f"Playbook '{playbook_id}' not found in pack {pack_id}")

    state["pack"]["playbook"] = selected
    logger.info("Pack resolved and inputs validated; strategy=%s", strategy)
    return state