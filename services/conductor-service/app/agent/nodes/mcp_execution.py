# services/conductor-service/app/agent/nodes/mcp_execution.py
from __future__ import annotations

import asyncio
import json
import logging
import random
import traceback
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from typing_extensions import Literal
from langgraph.types import Command

from app.db.run_repository import RunRepository
from app.models.run_models import StepAudit, ToolCallAudit
from app.agent.mcp.mcp_client import MCPConnection, MCPTransportConfig
from app.agent.mcp.json_utils import try_parse_json, get_by_dotted_path, coerce_list

logger = logging.getLogger("app.agent.nodes.mcp_execution")

_ASYNC_STATUS_SUFFIXES = (".status", ".check", ".poll", ".progress")
_JOB_ID_KEYS = ("job_id", "operation_id", "task_id", "id")

_RUNNING_STATES = {"queued", "running", "in_progress", "pending"}
_DONE_STATES = {"done", "completed", "succeeded", "success"}
_ERROR_STATES = {"error", "failed", "failure"}

_MAX_PAGES = 1000

# -------- helpers --------
def _extract_artifacts_from_output(output: Any, artifacts_path: str) -> List[Dict[str, Any]]:
    parsed = try_parse_json(output)
    candidates: List[Any] = []
    if artifacts_path:
        candidates.append(get_by_dotted_path(parsed, artifacts_path))
    for key in ("artifacts", "data.artifacts", "result.artifacts", "items"):
        candidates.append(get_by_dotted_path(parsed, key))
    first_present = next((c for c in candidates if c is not None), [])
    items = coerce_list(first_present)
    return [x for x in items if isinstance(x, dict)]

def _transport_from_capability(cap: Dict[str, Any]) -> MCPTransportConfig:
    exec_block = (cap.get("execution") or {})
    t = (exec_block.get("transport") or {})
    cfg = MCPTransportConfig(
        kind=(t.get("kind") or "http"),
        base_url=t.get("base_url"),
        headers=(t.get("headers") or {}),
        protocol_path=t.get("protocol_path") or "/mcp",
        verify_tls=t.get("verify_tls"),
        timeout_sec=t.get("timeout_sec") or 30,
    )
    # concise transport summary (no secrets)
    logger.info(
        "[mcp] transport cap_id=%s kind=%s base=%s path=%s timeout_s=%s tls=%s",
        cap.get("id") or cap.get("name") or "<unknown-cap>",
        cfg.kind,
        (cfg.base_url or "").rstrip("/"),
        cfg.protocol_path,
        cfg.timeout_sec,
        cfg.verify_tls,
    )
    return cfg

def _exec_block(cap: Dict[str, Any]) -> Dict[str, Any]:
    return (cap.get("execution") or {})

def _io_block(cap: Dict[str, Any]) -> Dict[str, Any]:
    return _exec_block(cap).get("io", {}) or {}

def _output_contract(cap: Dict[str, Any]) -> Dict[str, Any]:
    return _io_block(cap).get("output_contract", {}) or {}

def _artifacts_property(cap: Dict[str, Any]) -> str:
    return _output_contract(cap).get("artifacts_property", "artifacts")

def _tool_calls(cap: Dict[str, Any]) -> List[Dict[str, Any]]:
    return (_exec_block(cap).get("tool_calls") or [])

def _find_status_tool(cap: Dict[str, Any]) -> Optional[Tuple[str, Dict[str, Any]]]:
    def _requires_id(tc: Dict[str, Any]) -> bool:
        args_schema = tc.get("args_schema") or {}
        props = (args_schema.get("properties") or {})
        required = set(args_schema.get("required") or [])
        return any(k in props and k in required for k in _JOB_ID_KEYS)
    for tc in _tool_calls(cap):
        name = (tc.get("tool") or "").lower()
        if name.endswith(_ASYNC_STATUS_SUFFIXES) and _requires_id(tc):
            return tc.get("tool"), tc
    for tc in _tool_calls(cap):
        if _requires_id(tc):
            return tc.get("tool"), tc
    return None

def _detect_async_job(initial_result: Any) -> Tuple[Optional[str], Optional[str]]:
    payload = try_parse_json(initial_result)
    job_id = None
    for k in _JOB_ID_KEYS:
        v = get_by_dotted_path(payload, k)
        if isinstance(v, str) and v:
            job_id = v
            break
    status = get_by_dotted_path(payload, "status")
    if isinstance(job_id, str) and isinstance(status, str):
        return job_id, status.lower()
    return None, None

def _polling_settings(cap: Dict[str, Any]) -> Tuple[int, int, int]:
    ex = _exec_block(cap)
    p = (ex.get("polling") or {})
    return int(p.get("max_attempts", 120)), int(p.get("interval_ms", 1000)), int(p.get("jitter_ms", 250))

def _cap_timeout(cap: Dict[str, Any]) -> int:
    ts = _exec_block(cap).get("transport", {}).get("timeout_sec")
    return int(ts or 120)

def _supports_pagination(cap: Dict[str, Any]) -> bool:
    io = _io_block(cap)
    in_schema = (io.get("input_contract") or {}).get("json_schema") or {}
    in_props = (in_schema.get("properties") or {})
    if not any(k in in_props for k in ("cursor", "page_size")):
        return False
    extra = _output_contract(cap).get("extra_schema") or {}
    extra_props = (extra.get("properties") or {})
    return "next_cursor" in extra_props

def _extract_next_cursor(result: Any) -> Optional[str]:
    payload = try_parse_json(result)
    for key in ("next_cursor", "cursor.next", "nextPageToken", "page.next"):
        nxt = get_by_dotted_path(payload, key)
        if isinstance(nxt, str) and nxt.strip():
            return nxt.strip()
    return None

def _extract_progress(result: Any) -> Optional[float]:
    payload = try_parse_json(result)
    for key in ("progress", "data.progress", "result.progress", "meta.progress_percent"):
        prog = get_by_dotted_path(payload, key)
        try:
            if prog is not None:
                return float(prog)
        except Exception:
            pass
    return None

def _json_sample(val: Any, limit: int = 800) -> str:
    try:
        s = val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)
    except Exception:
        s = "<unserializable>"
    return s[:limit] + ("…" if len(s) > limit else "")

def _pick_id_arg_key_for_status_tool(status_tool_spec: Dict[str, Any]) -> Optional[str]:
    args_schema = status_tool_spec.get("args_schema") or {}
    props = (args_schema.get("properties") or {})
    required = set(args_schema.get("required") or [])
    for k in _JOB_ID_KEYS:
        if k in props and k in required:
            return k
    for k in _JOB_ID_KEYS:
        if k in props:
            return k
    return None

def _looks_like_missing_paths_root_error(t: str) -> bool:
    t = (t or "").lower()
    return "paths_root not found" in t or "no such file or directory" in t

# -------- node --------
def mcp_execution_node(*, runs_repo: RunRepository):
    async def _node(state: Dict[str, Any]) -> Command[Literal["capability_executor"]] | Dict[str, Any]:
        run = state["run"]
        run_uuid = UUID(run["run_id"])

        dispatch = state.get("dispatch") or {}
        step: Dict[str, Any] = dispatch.get("step") or {}
        capability: Dict[str, Any] = dispatch.get("capability") or {}
        resolved: Dict[str, Any] = dispatch.get("resolved") or {}

        step_id = step.get("id") or state.get("current_step_id") or "<unknown-step>"
        cap_id = capability.get("id") or "<unknown-cap>"

        tool_name: str = (resolved.get("tool_name") or "").strip()
        tool_args: Dict[str, Any] = resolved.get("args") or {}

        started = datetime.now(timezone.utc)
        artifacts_property = _artifacts_property(capability)

        # concise input snapshot
        logger.info(
            "[mcp] start step_id=%s cap_id=%s tool=%s args_keys=%d artifacts_prop=%s",
            step_id,
            cap_id,
            tool_name or "<missing>",
            len(tool_args.keys()),
            artifacts_property,
        )

        inputs_preview = {"tool_name": tool_name, "args": tool_args}

        if not tool_name:
            err = "[mcp] missing tool_name from resolver"
            await runs_repo.step_failed(run_uuid, step_id, error=err)
            return Command(goto="capability_executor", update={"dispatch": {}, "last_mcp_error": err})

        # transport
        try:
            transport_cfg = _transport_from_capability(capability)
        except Exception as e:
            err = f"invalid MCP transport for capability '{cap_id}': {e}"
            await runs_repo.append_step_audit(
                run_uuid,
                StepAudit(
                    step_id=step_id,
                    capability_id=cap_id,
                    mode="mcp",
                    inputs_preview=inputs_preview,
                    calls=[ToolCallAudit(
                        tool_name=tool_name,
                        tool_args_preview=tool_args,
                        raw_output_sample=str(e)[:400],
                        status="failed"
                    )],
                ),
            )
            await runs_repo.step_failed(run_uuid, step_id, error=err)
            return Command(goto="capability_executor", update={"dispatch": {}, "last_mcp_error": err})

        conn: Optional[MCPConnection] = None
        all_artifacts: List[Dict[str, Any]] = []
        call_audits: List[ToolCallAudit] = []

        try:
            conn = await MCPConnection.connect(transport_cfg)

            # initial call
            call_started = datetime.now(timezone.utc)
            raw_result: Any = None
            call_status: Literal["ok", "failed"] = "ok"
            validation_errors: List[str] = []

            try:
                raw_result = await conn.invoke_tool(tool_name, tool_args)
            except Exception as tool_err:
                call_status = "failed"
                msg = f"{type(tool_err).__name__}: {tool_err}"
                validation_errors = [msg]
                raw_result = {"error": str(tool_err)}
                logger.error("[mcp] tool_error tool=%s err=%s", tool_name, msg)

            duration_ms = int((datetime.now(timezone.utc) - call_started).total_seconds() * 1000)
            call_audits.append(
                ToolCallAudit(
                    tool_name=tool_name,
                    tool_args_preview=tool_args,
                    raw_output_sample=_json_sample(raw_result),
                    validation_errors=validation_errors,
                    duration_ms=duration_ms,
                    status=call_status,
                )
            )
            await runs_repo.append_tool_call_audit(run_uuid, step_id, call_audits[-1])

            if call_status == "failed":
                hint = None
                err_text = validation_errors[0] if validation_errors else ""
                if _looks_like_missing_paths_root_error(err_text):
                    hint = "Upstream repo snapshot incomplete or paths_root mismatch. Ensure s1 produced artifact.paths_root and it was propagated."

                await runs_repo.append_step_audit(
                    run_uuid,
                    StepAudit(
                        step_id=step_id,
                        capability_id=cap_id,
                        mode="mcp",
                        inputs_preview=inputs_preview,
                        calls=call_audits,
                        notes_md=(f"Hint: {hint}" if hint else None),
                    ),
                )
                await runs_repo.step_failed(run_uuid, step_id, error="MCP tool error")
                return Command(goto="capability_executor", update={"dispatch": {}, "last_mcp_error": "MCP tool error"})

            # first artifacts
            extracted = _extract_artifacts_from_output(raw_result, artifacts_property)
            if extracted:
                all_artifacts.extend(extracted)

            soft_deadline = started + timedelta(seconds=_cap_timeout(capability))
            max_attempts, interval_ms, jitter_ms = _polling_settings(capability)

            # async polling (lean logs)
            job_id, status = _detect_async_job(raw_result)
            status_tool = _find_status_tool(capability)
            attempts = 0

            if job_id and status and status_tool:
                status_tool_name, status_tool_spec = status_tool
                id_arg_key = _pick_id_arg_key_for_status_tool(status_tool_spec) or "job_id"
                logger.info("[mcp] async_detected job_id=%s status=%s status_tool=%s", job_id, status, status_tool_name)

                while status in _RUNNING_STATES:
                    attempts += 1
                    if attempts > max_attempts or datetime.now(timezone.utc) >= soft_deadline:
                        raise TimeoutError(f"Polling timeout for id={job_id} (status='{status}')")

                    await asyncio.sleep((interval_ms + random.randint(0, max(jitter_ms, 0))) / 1000.0)

                    poll_args = {id_arg_key: job_id}
                    poll_started = datetime.now(timezone.utc)
                    poll_raw: Any = await conn.invoke_tool(status_tool_name, poll_args)
                    poll_dur_ms = int((datetime.now(timezone.utc) - poll_started).total_seconds() * 1000)

                    call_audits.append(
                        ToolCallAudit(
                            tool_name=status_tool_name,
                            tool_args_preview=poll_args,
                            raw_output_sample=_json_sample(poll_raw),
                            validation_errors=[],
                            duration_ms=poll_dur_ms,
                            status="ok",
                        )
                    )
                    await runs_repo.append_tool_call_audit(run_uuid, step_id, call_audits[-1])

                    prog = _extract_progress(poll_raw)
                    if prog is not None and attempts % 5 == 0:
                        # throttle progress logs
                        logger.info("[mcp] progress job_id=%s attempts=%d progress=%.1f%%", job_id, attempts, prog)

                    _, status2 = _detect_async_job(poll_raw)
                    if status2:
                        status = status2

                    extracted = _extract_artifacts_from_output(poll_raw, artifacts_property)
                    if extracted:
                        all_artifacts.extend(extracted)

                if status in _ERROR_STATES:
                    raise RuntimeError(f"MCP job failed (id={job_id}, status={status})")
                logger.info("[mcp] async_complete job_id=%s status=%s attempts=%d artifacts_total=%d", job_id, status, attempts, len(all_artifacts))

            # pagination (lean logs)
            pages_fetched = 0
            if _supports_pagination(capability):
                next_cursor = _extract_next_cursor(raw_result)
                page_tool = status_tool[0] if job_id and status_tool else tool_name
                seen_cursors = set()
                while next_cursor:
                    if datetime.now(timezone.utc) >= soft_deadline:
                        raise TimeoutError(f"Pagination timeout; last cursor={next_cursor}")
                    if next_cursor in seen_cursors:
                        logger.warning("[mcp] pagination_duplicate_cursor cursor=%s", next_cursor)
                        break
                    if pages_fetched >= _MAX_PAGES:
                        logger.warning("[mcp] pagination_cap_reached max_pages=%d", _MAX_PAGES)
                        break
                    seen_cursors.add(next_cursor)

                    page_args = dict(tool_args)
                    page_args["cursor"] = next_cursor
                    pg_started = datetime.now(timezone.utc)
                    pg_raw = await conn.invoke_tool(page_tool, page_args)
                    pg_dur_ms = int((datetime.now(timezone.utc) - pg_started).total_seconds() * 1000)

                    call_audits.append(
                        ToolCallAudit(
                            tool_name=page_tool,
                            tool_args_preview=page_args,
                            raw_output_sample=_json_sample(pg_raw),
                            validation_errors=[],
                            duration_ms=pg_dur_ms,
                            status="ok",
                        )
                    )
                    await runs_repo.append_tool_call_audit(run_uuid, step_id, call_audits[-1])

                    extracted = _extract_artifacts_from_output(pg_raw, artifacts_property)
                    if extracted:
                        all_artifacts.extend(extracted)

                    next_cursor = _extract_next_cursor(pg_raw)
                    pages_fetched += 1

                logger.info("[mcp] pagination_done pages=%d artifacts_total=%d", pages_fetched, len(all_artifacts))
            else:
                pages_fetched = 0

            # finalize + DB audits
            await runs_repo.append_step_audit(
                run_uuid,
                StepAudit(
                    step_id=step_id,
                    capability_id=cap_id,
                    mode="mcp",
                    inputs_preview=inputs_preview,
                    calls=call_audits,
                ),
            )
            duration_ms_total = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
            await runs_repo.step_completed(
                run_uuid,
                step_id,
                metrics={"mode": "mcp", "duration_ms": duration_ms_total, "artifact_count": len(all_artifacts)},
            )

            # concise handoff summary
            logger.info(
                "[mcp] handoff step_id=%s cap_id=%s tool=%s calls=%d artifacts=%d pages=%d duration_ms=%d",
                step_id, cap_id, tool_name, len(call_audits), len(all_artifacts), pages_fetched, duration_ms_total
            )

            return Command(
                goto="capability_executor",
                update={
                    "dispatch": {},
                    "staged_artifacts": (state.get("staged_artifacts") or []) + all_artifacts,
                    "last_mcp_summary": {
                        "tool_calls": [
                            {"name": c.tool_name, "status": c.status, "duration_ms": c.duration_ms}
                            for c in call_audits
                        ],
                        "artifact_count": len(all_artifacts),
                        "completed_step_id": step_id,
                        "pages_fetched": pages_fetched,
                    },
                    "last_mcp_error": None,
                },
            )

        except Exception as e:
            tb = traceback.format_exc(limit=5)
            err_msg = f"MCP execution error: {e}"
            logger.error("[mcp] error step_id=%s cap_id=%s msg=%s", step_id, cap_id, err_msg)

            await runs_repo.append_step_audit(
                run_uuid,
                StepAudit(
                    step_id=step_id,
                    capability_id=cap_id,
                    mode="mcp",
                    inputs_preview=inputs_preview,
                    calls=call_audits or [ToolCallAudit(
                        tool_name=tool_name or "<unknown>",
                        tool_args_preview=tool_args,
                        raw_output_sample=(err_msg + " :: " + tb)[:800],
                        status="failed"
                    )],
                ),
            )
            await runs_repo.step_failed(run_uuid, step_id, error=err_msg)
            return Command(goto="capability_executor", update={"dispatch": {}, "last_mcp_error": err_msg})

        finally:
            try:
                if conn is not None:
                    await conn.aclose()
            except Exception:
                pass

    return _node