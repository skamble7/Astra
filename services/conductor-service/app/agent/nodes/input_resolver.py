# services/conductor-service/app/agent/nodes/input_resolver.py
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Awaitable, Callable as TCallable
from uuid import UUID as _UUID

from jsonschema import Draft202012Validator, ValidationError

from app.clients.artifact_service import ArtifactServiceClient
from app.clients.capability_service import CapabilityServiceClient
from app.db.run_repository import RunRepository
from app.models.run_models import StepState, StepStatus
from app.events.rabbit import get_bus, EventPublisher  # NEW

logger = logging.getLogger("app.agent.nodes.input_resolver")


def _json_preview(obj: Any, limit: int = 4000) -> str:
    """
    Best-effort compact preview for logging. Clipped to avoid massive log lines.
    """
    try:
        s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    except Exception:
        try:
            s = str(obj)
        except Exception:
            s = "<unserializable>"
    return s[:limit] + ("…" if len(s) > limit else "")


async def _try_call(method: Optional[TCallable[..., Awaitable[Any]]], *args, **kwargs) -> Optional[Any]:
    if not callable(method):
        return None
    try:
        return await method(*args, **kwargs)
    except Exception:
        # Keep quiet in normal ops; this is an internal probe helper.
        return None


async def _resolve_agent_capabilities(
    cap_client: CapabilityServiceClient,
    agent_cap_ids: List[str],
) -> List[Dict[str, Any]]:
    """
    Resolve agent capabilities using whatever surface the client exposes:
    - Prefer batch; fall back to single-by-id.
    - Best-effort: never raise; return successfully-resolved dicts.
    """
    resolved: List[Dict[str, Any]] = []
    if not agent_cap_ids:
        return resolved

    # Batch methods (first one that returns a non-empty list wins)
    batch_methods = [
        getattr(cap_client, "get_capabilities_by_ids", None),
        getattr(cap_client, "list_capabilities_by_ids", None),
        getattr(cap_client, "get_many_capabilities", None),
    ]
    for m in batch_methods:
        caps = await _try_call(m, agent_cap_ids)
        if isinstance(caps, list) and caps:
            return [c for c in caps if isinstance(c, dict)]

    # Single-by-id methods (first callable name used per id)
    single_methods = ["get_capability", "get_capability_resolved", "get_capability_by_id"]
    tasks = []
    for cid in agent_cap_ids:
        for name in single_methods:
            m = getattr(cap_client, name, None)
            if callable(m):
                tasks.append(_try_call(m, cid))
                break

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=False)
        for res in results:
            if isinstance(res, dict) and res.get("id"):
                resolved.append(res)

    return resolved


async def _resolve_input_contract(
    cap_client: CapabilityServiceClient,
    *,
    pack: Dict[str, Any],
    input_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    """
    Find the concrete input contract document for the playbook.
    Resolution order:
      1) If pack already carries a resolved list under 'pack_inputs', pick by id.
      2) If client exposes a getter, fetch by id.
      3) Best-effort: return None (validation will be soft if schema missing).
    """
    if not input_id:
        return None

    # 1) Look inside the resolved pack (if present)
    pack_inputs = pack.get("pack_inputs")
    if isinstance(pack_inputs, list) and pack_inputs:
        for it in pack_inputs:
            if isinstance(it, dict) and it.get("id") == input_id:
                return it

    # 2) Try client methods (be liberal in method names)
    candidates = [
        getattr(cap_client, "get_pack_input", None),
        getattr(cap_client, "get_input_contract", None),
        getattr(cap_client, "get_run_input_contract", None),
        getattr(cap_client, "get_form_by_id", None),
    ]
    for m in candidates:
        doc = await _try_call(m, input_id)
        if isinstance(doc, dict) and doc.get("id") == input_id:
            return doc

    return None


def input_resolver_node(
    *,
    runs_repo: RunRepository,
    cap_client: CapabilityServiceClient,
    art_client: ArtifactServiceClient,
    sha256_fingerprint: Callable[[Any], str],
):
    """
    Resolve the pack, validate inputs, prefetch artifact kind specs,
    and prime step state. Keep state lean; DB is the source of truth
    for step lifecycle.
    """

    async def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        logs: List[str] = state.get("logs", [])
        validations: List[Dict[str, Any]] = state.get("validations", [])
        request: Dict[str, Any] = state["request"]
        run_doc: Dict[str, Any] = state["run"]

        # --- NEW: Log the full request object (clipped) so we can verify it's in state
        try:
            logger.info("[input_resolver] state.request %s", _json_preview(request, 4000))
        except Exception:
            logger.exception("[input_resolver] failed to log state.request preview")

        pack_id: str = request["pack_id"]
        playbook_id: str = request["playbook_id"]
        inputs: Dict[str, Any] = request.get("inputs", {}) or {}
        model_id: Optional[str] = request.get("model_id")
        run_id = _UUID(run_doc["run_id"])
        workspace_id = run_doc["workspace_id"]
        strategy = (run_doc.get("strategy") or "").lower() or None
        correlation_id: Optional[str] = state.get("correlation_id")

        publisher = EventPublisher(bus=get_bus())

        # ------ Emit 'started' immediately (receipt) -------------------------
        await publisher.publish_once(
            runs_repo=runs_repo,
            run_id=run_id,
            event="started",
            payload={
                "run_id": str(run_id),
                "workspace_id": workspace_id,
                "playbook_id": playbook_id,
                "model_id": model_id,
                "received_at": state.get("started_at") or datetime.now(timezone.utc).isoformat(),
                "title": run_doc.get("title"),
                "description": run_doc.get("description"),
                "strategy": strategy,
            },
            workspace_id=workspace_id,
            playbook_id=playbook_id,
            strategy=strategy,
            emitter="input_resolver",
            correlation_id=correlation_id,
        )

        # --- Pack resolution -------------------------------------------------
        logs.append(f"Resolving pack '{pack_id}'…")
        pack = await cap_client.get_pack_resolved(pack_id)
        state["pack"] = pack

        # --- Playbook presence check ----------------------------------------
        pb = next((p for p in pack.get("playbooks", []) if p.get("id") == playbook_id), None)
        if not pb:
            msg = f"Playbook '{playbook_id}' not found in pack '{pack_id}'."
            validations.append({"severity": "high", "message": msg})

            await publisher.publish_once(
                runs_repo=runs_repo,
                run_id=run_id,
                event="inputs.resolved",
                payload={
                    "run_id": str(run_id),
                    "workspace_id": workspace_id,
                    "playbook_id": playbook_id,
                    "inputs_valid": False,
                    "errors": [msg],
                    "validations": validations,
                    "input_fingerprint": None,
                },
                workspace_id=workspace_id,
                playbook_id=playbook_id,
                strategy=strategy,
                emitter="input_resolver",
                correlation_id=correlation_id,
            )

            state.update(
                {
                    "inputs_valid": False,
                    "input_errors": [msg],
                    "validations": validations,
                    "logs": logs,
                    "agent_capabilities": [],
                    "agent_capabilities_map": {},
                }
            )
            try:
                logger.info(
                    "[input_resolver] final_state early_failure %s",
                    json.dumps(
                        {
                            "pack_id": pack_id,
                            "playbook_id": playbook_id,
                            "artifact_kinds_count": 0,
                            "agent_capabilities_count": 0,
                            "inputs_valid": False,
                        },
                        ensure_ascii=False,
                    ),
                )
            except Exception:
                logger.exception("[input_resolver] early_failure summary logging failed")
            return state

        # --- Agent capability resolution (for agent-side enrichment, etc.) ---
        agent_caps: List[Dict[str, Any]] = []
        pre_resolved = pack.get("agent_capabilities")
        if isinstance(pre_resolved, list) and pre_resolved:
            agent_caps = [c for c in pre_resolved if isinstance(c, dict)]
            logger.info("[input_resolver] agent_caps pre_resolved=%d", len(agent_caps))
        else:
            agent_cap_ids: List[str] = list(pack.get("agent_capability_ids") or [])
            if agent_cap_ids:
                agent_caps = await _resolve_agent_capabilities(cap_client, agent_cap_ids)
                missing = sorted(set(agent_cap_ids) - set([c.get("id") for c in agent_caps if c.get("id")]))
                logger.info(
                    "[input_resolver] agent_caps requested=%d resolved=%d missing=%d",
                    len(agent_cap_ids), len(agent_caps), len(missing),
                )
                if missing:
                    validations.append({"severity": "medium", "message": f"Unresolved agent capabilities: {missing}"})
            else:
                logger.info("[input_resolver] agent_caps requested=0 resolved=0")

        agent_caps_map: Dict[str, Dict[str, Any]] = {}
        for c in agent_caps:
            cid = c.get("id")
            if isinstance(cid, str) and cid and cid not in agent_caps_map:
                agent_caps_map[cid] = c

        # --- Pack & playbook input wiring (new model) ------------------------
        pack_input_ids = list(pack.get("pack_input_ids") or [])
        playbook_input_id: Optional[str] = pb.get("input_id")

        try:
            pack_preview = {
                "pack_id": pack.get("pack_id") or pack_id,
                "version": pack.get("version"),
                "capability_ids_count": len(list(pack.get("capability_ids") or [])),
                "agent_capability_ids_count": len(list(pack.get("agent_capability_ids") or [])),
                "capabilities_count": len(pack.get("capabilities") or []),
                "agent_capabilities_count": len(pack.get("agent_capabilities") or []),
                "playbooks_count": len(pack.get("playbooks") or []),
                "pack_input_ids_count": len(pack_input_ids),
                "playbook_input_id": playbook_input_id,
            }
            logger.info("[input_resolver] pack_resolved %s", json.dumps(pack_preview, ensure_ascii=False))
        except Exception:
            logger.exception("[input_resolver] pack_resolved summary logging failed")

        # Validate playbook.input_id against pack.pack_input_ids
        if playbook_input_id and pack_input_ids and playbook_input_id not in pack_input_ids:
            validations.append({
                "severity": "high",
                "message": f"Playbook input_id '{playbook_input_id}' is not listed in pack.pack_input_ids."
            })

        # --- Artifact kind specs (union from pack capabilities) --------------
        caps: List[Dict[str, Any]] = pack.get("capabilities", []) or []
        produces: List[str] = []
        for c in caps:
            for k in c.get("produces_kinds", []) or []:
                if k not in produces:
                    produces.append(k)

        kinds_map: Dict[str, Dict[str, Any]] = {}
        failures = 0

        if produces:
            async def _fetch_kind(kind_id: str) -> tuple[str, Dict[str, Any]]:
                data = await art_client.registry_get_kind(kind_id)
                return kind_id, data

            results = await asyncio.gather(*[_fetch_kind(k) for k in produces], return_exceptions=True)
            for res in results:
                if isinstance(res, Exception):
                    failures += 1
                else:
                    kind_id, data = res
                    kinds_map[kind_id] = data

        logger.info(
            "[input_resolver] kinds fetch requested=%d resolved=%d failed=%d",
            len(produces),
            len(kinds_map),
            failures,
        )
        if failures:
            validations.append({"severity": "high", "message": f"Failed to load {failures} artifact kind spec(s)"})

        # --- Input validation against the selected input contract ------------
        errors: List[str] = []
        inputs_valid = True

        input_contract = await _resolve_input_contract(cap_client, pack=pack, input_id=playbook_input_id)
        if not input_contract:
            validations.append({
                "severity": "low",
                "message": "Input contract not found/resolved; skipping strict validation."
            })
            json_schema = {}
        else:
            json_schema = (input_contract.get("json_schema") or {})

        if json_schema:
            try:
                Draft202012Validator(json_schema).validate(
                    {"inputs": inputs}
                    if ("properties" in json_schema and "inputs" in json_schema.get("properties", {}))
                    else inputs
                )
            except ValidationError as ve:
                inputs_valid = False
                errors.append(ve.message)
        else:
            # no schema -> keep inputs_valid True but note it
            validations.append({"severity": "low", "message": "Pack/playbook input schema missing; skipping strict validation."})

        # Fingerprint only if valid to avoid misleading hashes
        fingerprint = sha256_fingerprint(inputs) if inputs_valid else None

        # --- Initialize steps in DB -----------------------------------------
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

        if steps_for_db:
            await runs_repo.init_steps(run_id, steps_for_db)

        # Persist run input metadata (store the concrete playbook-level input_id)
        await runs_repo._col.update_one(  # using DAL's collection per current design
            {"run_id": str(run_id)},
            {"$set": {
                "pack_input_id": playbook_input_id,  # keep name for backward-compat; value now sourced from playbook.input_id
                "inputs": inputs,
                "input_fingerprint": fingerprint
            }},
        )

        logger.info(
            "[input_resolver] db_init steps=%d inputs_valid=%s fingerprint=%s",
            len(steps_for_db),
            inputs_valid,
            (fingerprint[:8] if isinstance(fingerprint, str) else None),
        )

        # --- Emit inputs.resolved -------------------------------------------
        await publisher.publish_once(
            runs_repo=runs_repo,
            run_id=run_id,
            event="inputs.resolved",
            payload={
                "run_id": str(run_id),
                "workspace_id": workspace_id,
                "playbook_id": playbook_id,
                "inputs_valid": inputs_valid,
                "errors": errors,
                "validations": validations,
                "input_fingerprint": fingerprint,
                # optional visibility:
                "pack_input_ids": pack_input_ids,
                "playbook_input_id": playbook_input_id,
            },
            workspace_id=workspace_id,
            playbook_id=playbook_id,
            strategy=strategy,
            emitter="input_resolver",
            correlation_id=correlation_id,
        )

        # --- Minimal state handoff ------------------------------------------
        state.update(
            {
                "pack": pack,
                "artifact_kinds": kinds_map,
                "agent_capabilities": agent_caps,
                "agent_capabilities_map": agent_caps_map,
                "inputs_valid": inputs_valid,
                "input_errors": errors,
                "input_fingerprint": fingerprint,
                "logs": logs,
                "validations": validations,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        # Final concise summary (handover snapshot)
        try:
            summary = {
                "pack_id": pack_id,
                "playbook_id": playbook_id,
                "capabilities_count": len(pack.get("capabilities") or []),
                "agent_capabilities_count": len(agent_caps),
                "artifact_kinds_count": len(kinds_map),
                "inputs_keys": sorted(list(inputs.keys())),
                "inputs_valid": inputs_valid,
                "playbook_input_id": playbook_input_id,
            }
            logger.info("[input_resolver] handoff %s", json.dumps(summary, ensure_ascii=False))
        except Exception:
            logger.exception("[input_resolver] handoff summary logging failed")

        return state

    return _node