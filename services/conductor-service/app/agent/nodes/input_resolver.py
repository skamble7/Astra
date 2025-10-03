# services/conductor-service/app/agent/nodes/input_resolver.py
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List

from jsonschema import Draft202012Validator, ValidationError

from app.clients.artifact_service import ArtifactServiceClient
from app.clients.capability_service import CapabilityServiceClient
from app.db.run_repository import RunRepository
from app.models.run_models import StepState, StepStatus

logger = logging.getLogger("app.agent.nodes.input_resolver")


def input_resolver_node(
    *,
    runs_repo: RunRepository,
    cap_client: CapabilityServiceClient,
    art_client: ArtifactServiceClient,
    sha256_fingerprint: Callable[[Any], str],
):
    """
    Returns an async node function suitable for LangGraph.
    Minimal state in/out; DB holds step state. We keep only what's needed for
    downstream nodes (pack, artifact_kinds, validation results).
    """

    async def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        logs: List[str] = state.get("logs", [])
        validations: List[Dict[str, Any]] = state.get("validations", [])
        request: Dict[str, Any] = state["request"]
        run_doc: Dict[str, Any] = state["run"]

        pack_id: str = request["pack_id"]
        playbook_id: str = request["playbook_id"]
        inputs: Dict[str, Any] = request.get("inputs", {}) or {}

        # 1) Resolve pack (with capabilities & pack_input)
        logs.append(f"Resolving pack '{pack_id}'…")
        pack = await cap_client.get_pack_resolved(pack_id)
        state["pack"] = pack

        # Sanity: playbook exists
        pb = next((p for p in pack.get("playbooks", []) if p.get("id") == playbook_id), None)
        if not pb:
            msg = f"Playbook '{playbook_id}' not found in pack '{pack_id}'."
            validations.append({"severity": "high", "message": msg})
            state.update({"inputs_valid": False, "input_errors": [msg], "validations": validations, "logs": logs})
            # Log the state even on early exit for troubleshooting
            try:
                logger.info(
                    "input_resolver FINAL STATE (early failure): %s",
                    json.dumps(state, ensure_ascii=False, default=str),
                )
            except Exception:
                logger.exception("Failed to serialize state for logging (early failure).")
            return state

        # 2) Artifact kinds (union of all produces_kinds across capabilities)
        caps: List[Dict[str, Any]] = pack.get("capabilities", []) or []
        produces: List[str] = []
        for c in caps:
            for k in c.get("produces_kinds", []) or []:
                if k not in produces:
                    produces.append(k)

        async def _fetch_kind(kind_id: str) -> tuple[str, Dict[str, Any]]:
            data = await art_client.registry_get_kind(kind_id)
            return kind_id, data

        logs.append(f"Fetching {len(produces)} artifact kind specs…")
        kinds_map: Dict[str, Dict[str, Any]] = {}
        if produces:
            results = await asyncio.gather(*[_fetch_kind(k) for k in produces], return_exceptions=True)
            for res in results:
                if isinstance(res, Exception):
                    validations.append({"severity": "high", "message": f"Failed to load a kind: {res}"})
                else:
                    kind_id, data = res
                    kinds_map[kind_id] = data

        # 3) Validate inputs against pack_input.json_schema
        pack_input = pack.get("pack_input") or {}
        json_schema = (pack_input.get("json_schema") or {})
        errors: List[str] = []
        inputs_valid = True

        if json_schema:
            try:
                # Some pack inputs wrap the contract under an "inputs" property; honor that if present.
                Draft202012Validator(json_schema).validate(
                    {"inputs": inputs}
                    if ("properties" in json_schema and "inputs" in json_schema.get("properties", {}))
                    else inputs
                )
            except ValidationError as ve:
                inputs_valid = False
                errors.append(ve.message)
        else:
            # If schema missing, treat as warning, not failure
            validations.append(
                {"severity": "low", "message": "Pack input schema missing; skipping strict validation."}
            )

        # 4) Compute fingerprint if valid
        fingerprint = None
        if inputs_valid:
            fingerprint = sha256_fingerprint(inputs)

        # 5) Initialize steps in DB (but do NOT keep them in the graph state)
        steps_for_db: List[StepState] = []
        for s in pb.get("steps", []):
            steps_for_db.append(
                StepState(
                    step_id=s["id"],
                    capability_id=s["capability_id"],
                    name=s.get("name"),
                    status=StepStatus.PENDING,
                )
            )

        # 6) Update run doc (steps + input fingerprint) in DB
        from uuid import UUID as _UUID
        run_id = _UUID(run_doc["run_id"])
        if steps_for_db:
            await runs_repo.init_steps(run_id, steps_for_db)
        await runs_repo._col.update_one(  # using DAL's collection to avoid a full "update" method right now
            {"run_id": str(run_id)},
            {
                "$set": {
                    "pack_input_id": pack.get("pack_input_id"),
                    "inputs": inputs,
                    "input_fingerprint": fingerprint,
                }
            },
        )

        # 7) Store only the minimal, non-redundant state
        state.update(
            {
                "pack": pack,                     # contains capabilities/playbooks/pack_input
                "artifact_kinds": kinds_map,      # resolved kind specs
                "inputs_valid": inputs_valid,
                "input_errors": errors,
                "input_fingerprint": fingerprint,
                "logs": logs,
                "validations": validations,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        # 8) Log the entire final (trimmed) state for verification
        try:
            logger.info("input_resolver FINAL STATE: %s", json.dumps(state, ensure_ascii=False, default=str))
        except Exception:
            # Avoid failing the run because of logging serialization issues
            logger.exception("Failed to serialize state for logging.")

        return state

    return _node