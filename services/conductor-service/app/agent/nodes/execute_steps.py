# services/conductor-service/app/agent/nodes/execute_steps.py
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.clients.artifact_service import ArtifactServiceClient
from app.db.mongodb import get_client
from app.db.run_repository import RunRepository
from app.events.rabbit import get_bus
from app.llm.factory import get_agent_llm
from app.models.run_models import ArtifactEnvelope, ArtifactProvenance, StepStatus, ToolCallAudit
from app.config import settings

logger = logging.getLogger("app.agent.nodes.execute")


def _json_preview(obj: Any, limit: int = 1200) -> Any:
    try:
        s = json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        s = str(obj)
    return s if len(s) <= limit else s[:limit] + f"...(+{len(s)-limit}B)"


async def _synthesize_tool_args_with_llM(
    *,
    step: Dict[str, Any],
    capability: Dict[str, Any],
    inputs: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Use the agent LLM to produce tool arguments given the capability's args_schema + step.params + inputs.
    """
    llm = get_agent_llm()
    tool_calls = (capability.get("execution", {}).get("tool_calls") or [])
    if not tool_calls:
        args = step.get("params") or {}
        logger.debug("LLM synthesis skipped (no tool_calls). Using step.params=%s", _json_preview(args))
        return args

    # Use the first tool's schema as the "shape"
    tc = tool_calls[0]
    args_schema = tc.get("args_schema") or {"type": "object", "additionalProperties": True}
    seed = {
        "capability_id": capability.get("id"),
        "step_params": step.get("params") or {},
        "inputs": inputs or {},
        "hint": "Produce minimal, valid JSON for the tool call args schema. Do not include nulls.",
    }
    prompt = (
        "You are an orchestration agent. Given the capability step parameters and run inputs, "
        "produce JSON arguments for the MCP tool call strictly conforming to the JSON Schema.\n\n"
        f"Context:\n{json.dumps(seed, ensure_ascii=False, indent=2)}\n\n"
        "Return ONLY the JSON object."
    )
    res = await llm.acomplete_json(prompt, schema={"name": "Args", "schema": args_schema})
    try:
        args = json.loads(res.text)
        logger.info("Synthesized tool args via LLM: %s", _json_preview(args))
        return args
    except Exception:
        # fallback to direct params
        logger.warning("LLM tool-args synthesis failed; using step.params")
        return step.get("params") or {}


def _extract_job_id(pages: List[Dict[str, Any]]) -> Optional[str]:
    """
    Try to pull a job id from:
      - structured.data fields (job_id / id)
      - text content blocks (JSON or plain text with 'job_id: <...>' or UUID-like)
    """
    for pg in pages:
        datum = (pg or {}).get("data") or {}
        structured = datum.get("structured")
        if isinstance(structured, dict):
            for key in ("job_id", "id", "jobId"):
                if structured.get(key):
                    return str(structured[key])

        for block in (datum.get("content") or []):
            if isinstance(block, dict) and block.get("type") == "text":
                txt = str(block.get("text", "")).strip()
                # try JSON parse
                try:
                    obj = json.loads(txt)
                    if isinstance(obj, dict):
                        for key in ("job_id", "id", "jobId"):
                            if obj.get(key):
                                return str(obj[key])
                except Exception:
                    pass
                # try patterns
                m = re.search(r"(?:job[_\s-]?id)\s*[:=]\s*([A-Za-z0-9._-]+)", txt, re.I)
                if m:
                    return m.group(1)
                m2 = re.search(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", txt, re.I)
                if m2:
                    return m2.group(0)
    return None


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
    """
    produced: List[ArtifactEnvelope] = []
    produces_kinds = capability.get("produces_kinds") or []
    schema_version = "1.0.0"

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
                    pass

    return produced


async def execute_steps(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Iterate playbook steps; execute MCP/LLM branches; enrich, validate, collect.
    Handles 2-phase MCP flows (start/status poll) automatically.
    """
    run_id = UUID(state["run"]["run_id"])
    client = get_client()
    repo = RunRepository(client, db_name=settings.mongo_db)
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
                args = await _synthesize_tool_args_with_llM(step=step, capability=capability, inputs=inputs)
                logger.info("Prepared tool args for %s: %s", cap_id, _json_preview(args))

                tool_calls = exec_cfg.get("tool_calls") or []
                if not tool_calls:
                    raise RuntimeError(f"Capability {cap_id} has no tool_calls")

                client_rec = state["mcp"]["clients"].get(cap_id)
                if not client_rec:
                    raise RuntimeError(f"No MCP client initialized for capability {cap_id}")
                mcp_client = client_rec["client"]

                # default workspace hint if provided via inputs.extra_context
                extra_ctx = ((inputs or {}).get("inputs") or {}).get("extra_context") or {}
                default_workspace = extra_ctx.get("workspace_mount")
                if default_workspace and "volume_path" not in args:
                    args["volume_path"] = default_workspace
                    logger.info("volume_path not provided; defaulting to workspace_mount=%s", default_workspace)

                # Figure out if this is a 2-phase flow
                # We detect a start/status pair by tool name suffixes if two tools exist.
                tools_available = [t for t in (state["mcp"]["discovery_reports"].get(cap_id, {}).get("tools") or [])]
                logger.info("Capability %s discovery tools=%s", cap_id, tools_available)

                def _find_tool(name_substr: str) -> Optional[str]:
                    for t in tools_available:
                        if name_substr in t:
                            return t
                    for t in [tc.get("tool") for tc in tool_calls if tc.get("tool")]:
                        if name_substr in t:
                            return t
                    return None

                start_tool = _find_tool(".start") or _find_tool("snapshot.start")
                status_tool = _find_tool(".status") or _find_tool("snapshot.status")

                # Fallback to first tool if no pair detected
                if not start_tool and tool_calls:
                    start_tool = tool_calls[0]["tool"]

                # Timeouts per tool spec, fallback to transport timeout
                def _timeout_for(tool_name: str) -> int:
                    for tc in tool_calls:
                        if tc.get("tool") == tool_name:
                            return int(tc.get("timeout_sec", exec_cfg.get("transport", {}).get("timeout_sec", 120)))
                    return int(exec_cfg.get("transport", {}).get("timeout_sec", 120))

                pages_accum: List[Dict[str, Any]] = []

                # 1) call start
                logger.info("Invoking start tool=%s with args=%s", start_tool, _json_preview(args))
                start_res = await mcp_client.call_tool(start_tool, args, timeout_sec=_timeout_for(start_tool))
                start_pages = start_res.get("pages") or []
                pages_accum.extend(start_pages)

                job_id = _extract_job_id(start_pages)
                logger.info("Start returned job_id=%s (raw pages=%s)", job_id, _json_preview(start_pages))

                # 2) if we have a status tool + job_id -> poll
                if job_id and status_tool:
                    poll_args = {"job_id": job_id}
                    max_polls = int(exec_cfg.get("polling", {}).get("max_attempts", 30))
                    poll_delay = float(exec_cfg.get("polling", {}).get("interval_sec", 2.0))

                    logger.info("Polling status via tool=%s (max=%s, interval=%ss)", status_tool, max_polls, poll_delay)
                    for i in range(max_polls):
                        res = await mcp_client.call_tool(status_tool, poll_args, timeout_sec=_timeout_for(status_tool))
                        pages = res.get("pages") or []
                        pages_accum.extend(pages)

                        # Heuristic: if any page structured has a 'status' and it's in terminal states, stop.
                        terminal = False
                        done = False
                        for pg in pages:
                            st = (((pg or {}).get("data") or {}).get("structured") or {}) or {}
                            if isinstance(st, dict):
                                status_val = str(st.get("status") or st.get("state") or "").lower()
                                if status_val in {"done", "success", "completed", "complete"}:
                                    terminal = True
                                    done = True
                                elif status_val in {"failed", "error"}:
                                    terminal = True
                                    done = False
                        logger.info("Poll %d/%d -> terminal=%s", i + 1, max_polls, terminal)
                        if terminal:
                            break
                        await asyncio.sleep(poll_delay)

                call_audit.tool_name = start_tool
                call_audit.tool_args_preview = (args if len(_json_preview(args)) < 1200 else {"_size": len(str(args))})

                produced_artifacts = await _normalize_tool_output_to_artifacts(
                    pages=pages_accum,
                    capability=capability,
                    run_meta={"run_id": state["run"]["run_id"], "step_id": step_id, "capability_id": cap_id},
                )

            elif exec_cfg.get("mode") == "llm":
                llm = get_agent_llm()
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

            # Validation
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
            logger.exception("Step failed: step_id=%s cap_id=%s error=%s", step_id, cap_id, e)
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
            state["error"] = str(e)
            return state  # edge to handle_error

    return state