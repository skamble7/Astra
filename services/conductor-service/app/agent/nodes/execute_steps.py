# services/conductor-service/app/agent/nodes/execute_steps.py
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import UUID

from app.clients.artifact_service import ArtifactServiceClient
from app.db.mongodb import get_client
from app.db.run_repository import RunRepository
from app.events.rabbit import get_bus
from app.llm.factory import get_agent_llm
from app.mcp_host.invoker import CancelToken, invoke_tool_call
from app.mcp_host.types import ToolCallSpec
from app.models.run_models import ArtifactEnvelope, ArtifactProvenance, StepStatus, ToolCallAudit

logger = logging.getLogger("app.agent.nodes.execute")


async def _synthesize_tool_args_with_llm(*, step: Dict[str, Any], capability: Dict[str, Any], inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Use the agent LLM to produce tool arguments given the capability's args_schema + step.params + inputs.
    This keeps the executor flexible across MCP tools.
    """
    llm = get_agent_llm()
    tool_calls = (capability.get("execution", {}).get("tool_calls") or [])
    if not tool_calls:
        return step.get("params") or {}

    # For now assume one tool per step; if multiple tools, we pick the first to synthesize args.
    tc = tool_calls[0]
    args_schema = tc.get("args_schema") or {"type": "object", "additionalProperties": True}
    seed = {
        "capability_id": capability["id"],
        "step_params": step.get("params") or {},
        "inputs": inputs or {},
        "hint": "Produce minimal, valid JSON for the tool call args schema. Do not include nulls."
    }
    prompt = (
        "You are an orchestration agent. Given the capability step parameters and run inputs, "
        "produce JSON arguments for the MCP tool call strictly conforming to the JSON Schema.\n\n"
        f"Context:\n{json.dumps(seed, ensure_ascii=False, indent=2)}\n\n"
        "Return ONLY the JSON object."
    )
    res = await llm.acomplete_json(prompt, schema={"name": "Args", "schema": args_schema})
    try:
        return json.loads(res.text)
    except Exception:
        # fallback to direct params
        logger.warning("LLM tool-args synthesis failed; using step.params")
        return step.get("params") or {}


async def _normalize_tool_output_to_artifacts(
    *,
    pages: List[Dict[str, Any]],
    capability: Dict[str, Any],
    run_meta: Dict[str, Any],
) -> List[ArtifactEnvelope]:
    """
    Best-effort normalization:
      - If structured data exists under `structured`, treat it as a list of artifact items or a single item.
      - Otherwise attempt to parse `content` blocks (text/json) heuristically.
    The exact shape will depend on each MCP server; refine as needed.
    """
    produced: List[ArtifactEnvelope] = []
    produces_kinds = capability.get("produces_kinds") or []
    schema_version = "1.0.0"  # rely on registry later if provided

    def make_env(item: Dict[str, Any]) -> ArtifactEnvelope:
        kind_id = item.get("kind") or (produces_kinds[0] if produces_kinds else "cam.generic.unknown")
        identity = item.get("identity") or item.get("key") or {"name": item.get("name", "unknown")}
        data = item.get("data") or item
        return ArtifactEnvelope(
            kind_id=kind_id,
            schema_version=schema_version,
            identity=identity,
            data=data,
            provenance=ArtifactProvenance(
                run_id=UUID(run_meta["run_id"]),
                step_id=run_meta["step_id"],
                capability_id=run_meta["capability_id"],
                mode="mcp",
            ),
        )

    for pg in pages:
        datum = pg.get("data") if isinstance(pg, dict) else {}
        structured = datum.get("structured")
        if structured is not None:
            if isinstance(structured, list):
                for it in structured:
                    if isinstance(it, dict):
                        produced.append(make_env(it))
            elif isinstance(structured, dict):
                produced.append(make_env(structured))
            continue

        # else, try parsing content blocks (text that might be JSON)
        content = datum.get("content") or []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text" and "text" in block:
                txt = block["text"]
                try:
                    obj = json.loads(txt)
                    if isinstance(obj, list):
                        for it in obj:
                            if isinstance(it, dict):
                                produced.append(make_env(it))
                    elif isinstance(obj, dict):
                        produced.append(make_env(obj))
                except Exception:
                    # ignore non-JSON
                    pass

    return produced


async def execute_steps(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Iterate playbook steps; execute MCP/LLM branches; enrich, validate, collect.
    """
    run_id = UUID(state["run"]["run_id"])
    client = get_client()
    repo = RunRepository(client, db_name=client.get_default_database().name)
    bus = get_bus()

    cap_by_id = state["pack"]["capabilities_by_id"]
    playbook = state["pack"]["playbook"]
    inputs = state["inputs"]["raw"]

    for step in (playbook.get("steps") or []):
        step_id = step["id"]
        cap_id = step["capability_id"]
        capability = cap_by_id[cap_id]
        exec_cfg = capability.get("execution") or {}

        # emit step.started
        await repo.step_started(run_id, step_id)
        await bus.publish(
            service="conductor",
            event="step.started",
            payload={
                "run_id": str(run_id),
                "workspace_id": state["run"]["workspace_id"],
                "playbook_id": state["run"]["playbook_id"],
                "step": {"id": step_id, "capability_id": cap_id, "name": step.get("name")},
                "params": step.get("params") or {},
                "started_at": datetime.now(timezone.utc).isoformat(),
                "produces_kinds": capability.get("produces_kinds") or [],
                "status": "started",
            },
        )

        try:
            produced_artifacts: List[ArtifactEnvelope] = []
            call_audit = ToolCallAudit()

            if exec_cfg.get("mode") == "mcp":
                # build args (LLM-assisted)
                args = await _synthesize_tool_args_with_llm(step=step, capability=capability, inputs=inputs)

                # For now assume the first tool_call
                tool_calls = exec_cfg.get("tool_calls") or []
                if not tool_calls:
                    raise RuntimeError(f"Capability {cap_id} has no tool_calls")

                tc = tool_calls[0]
                spec = ToolCallSpec(
                    tool=tc["tool"],
                    args_schema=tc.get("args_schema"),
                    output_kinds=tc.get("output_kinds") or [],
                    timeout_sec=int(tc.get("timeout_sec", 60)),
                    retries=int(tc.get("retries", 1)),
                    expects_stream=bool(tc.get("expects_stream", False)),
                    cancellable=bool(tc.get("cancellable", True)),
                )

                # invoke via MCP client
                client_rec = state["mcp"]["clients"].get(cap_id)
                if not client_rec:
                    raise RuntimeError(f"No MCP client initialized for capability {cap_id}")
                client_obj = client_rec["client"]

                cancel = CancelToken()
                result = await invoke_tool_call(client=client_obj, spec=spec, args=args, cancel=cancel)

                pages_dicts = []
                if result.stream is not None:
                    # We surface a runtime error earlier, but keep safety here
                    async for _ in result.stream:
                        pass
                else:
                    pages_dicts = [{"data": p.data, "cursor": p.cursor} for p in result.pages]

                call_audit.tool_name = spec.tool
                call_audit.tool_args_preview = (args if len(str(args)) < 1200 else {"_size": len(str(args))})

                produced_artifacts = await _normalize_tool_output_to_artifacts(
                    pages=pages_dicts, capability=capability, run_meta={"run_id": state["run"]["run_id"], "step_id": step_id, "capability_id": cap_id}
                )

            elif exec_cfg.get("mode") == "llm":
                # use capability-specified LLM (future); for now, fallback to agent LLM
                from app.llm.factory import get_agent_llm
                llm = get_agent_llm()

                # Minimal prompt: real system should load prompt from registry kind.prompt
                prompt = (
                    "Produce artifacts for the given capability based on inputs.\n"
                    f"Capability ID: {cap_id}\n"
                    f"Inputs JSON:\n{json.dumps(inputs, ensure_ascii=False)}\n"
                    "Return a JSON object { items: [ { kind, identity, data } ... ] }"
                )
                res = await llm.acomplete_json(
                    prompt,
                    schema={
                        "name": "Artifacts",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "items": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "required": ["kind", "identity", "data"],
                                        "properties": {
                                            "kind": {"type": "string"},
                                            "identity": {"type": "object"},
                                            "data": {"type": "object"},
                                        },
                                        "additionalProperties": True,
                                    },
                                }
                            },
                            "required": ["items"],
                            "additionalProperties": False,
                        },
                    },
                )
                body = {}
                try:
                    body = json.loads(res.text)
                except Exception:
                    body = {"items": []}
                items = body.get("items", [])
                for it in items:
                    produced_artifacts.append(
                        ArtifactEnvelope(
                            kind_id=it.get("kind"),
                            schema_version="1.0.0",
                            identity=it.get("identity") or {},
                            data=it.get("data") or {},
                            provenance=ArtifactProvenance(
                                run_id=UUID(state["run"]["run_id"]),
                                step_id=step_id,
                                capability_id=cap_id,
                                mode="llm",
                            ),
                        )
                    )
                call_audit.system_prompt = "You are the conductor agent."
                call_audit.user_prompt = prompt
                call_audit.llm_config = {"provider": "agent", "model": state.get("llm", {}).get("model")}

            else:
                raise RuntimeError(f"Unsupported execution mode for capability {cap_id}: {exec_cfg.get('mode')}")

            # Enrichment (diagrams/narratives)
            from app.core.enrichment.diagrams import enrich_diagrams
            from app.core.enrichment.narratives import enrich_narratives
            produced_artifacts = await enrich_diagrams(produced_artifacts, state["registry"]["kinds_by_id"])
            produced_artifacts = await enrich_narratives(produced_artifacts, state["registry"]["kinds_by_id"])

            # Validation (against registry schemas via artifact-service validate endpoint)
            from app.core.validation import validate_artifacts
            validations, valid_artifacts = await validate_artifacts(produced_artifacts)

            state["aggregates"]["validations"].extend(validations)
            state["aggregates"]["run_artifacts"].extend(valid_artifacts)

            # persist progress in DAL
            await repo.append_run_artifacts(run_id, valid_artifacts)
            await repo.append_tool_call_audit(run_id, step_id, call_audit)
            await repo.step_completed(run_id, step_id)

            # events
            await bus.publish(
                service="conductor",
                event="step.completed",
                payload={
                    "run_id": str(run_id),
                    "workspace_id": state["run"]["workspace_id"],
                    "playbook_id": state["run"]["playbook_id"],
                    "step": {"id": step_id, "capability_id": cap_id, "name": step.get("name")},
                    "ended_at": datetime.now(timezone.utc).isoformat(),
                    "duration_s": None,
                    "status": "completed",
                },
            )

        except Exception as e:
            # step failed
            await repo.step_failed(run_id, step_id, error=str(e))
            await bus.publish(
                service="conductor",
                event="step.failed",
                payload={
                    "run_id": str(run_id),
                    "workspace_id": state["run"]["workspace_id"],
                    "playbook_id": state["run"]["playbook_id"],
                    "step": {"id": step_id, "capability_id": cap_id, "name": step.get("name")},
                    "ended_at": datetime.now(timezone.utc).isoformat(),
                    "duration_s": None,
                    "error": str(e),
                    "status": "failed",
                },
            )
            # short-circuit to error handler node
            state["error"] = str(e)
            return state  # edge to handle_error

    return state