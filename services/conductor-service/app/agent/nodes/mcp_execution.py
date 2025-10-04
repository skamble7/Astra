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
    logger.info(
        "[MCP] Transport for capability %s: kind=%s base=%s protocol_path=%s timeout=%s verify_tls=%s",
        cap.get("id") or cap.get("name"),
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

def _json_sample(val: Any, limit: int = 1200) -> str:
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

        # Read-only view of selection
        dispatch = state.get("dispatch") or {}
        step: Dict[str, Any] = dispatch.get("step") or {}
        capability: Dict[str, Any] = dispatch.get("capability") or {}
        resolved: Dict[str, Any] = dispatch.get("resolved") or {}

        # Fallback to current_step_id to avoid "<unknown-step>"
        step_id = step.get("id") or state.get("current_step_id") or "<unknown-step>"
        cap_id = capability.get("id") or "<unknown-cap>"

        tool_name: str = (resolved.get("tool_name") or "").strip()
        tool_args: Dict[str, Any] = resolved.get("args") or {}

        started = datetime.now(timezone.utc)
        artifacts_property = _artifacts_property(capability)
        logger.info("[MCP] Step %s (%s): artifacts_property='%s'", step_id, cap_id, artifacts_property)

        inputs_preview = {"tool_name": tool_name, "args": tool_args}

        if not tool_name:
            err = "[MCP] No tool_name provided by mcp_input_resolver."
            logger.error(err)
            await runs_repo.step_failed(run_uuid, step_id, error=err)
            # Do NOT write current_step_id here
            return Command(goto="capability_executor", update={
                "dispatch": {},
                "last_mcp_error": err,
            })

        try:
            transport_cfg = _transport_from_capability(capability)
        except Exception as e:
            err = f"Invalid MCP transport for capability '{cap_id}': {e}"
            logger.exception("[MCP] %s", err)
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
            return Command(goto="capability_executor", update={
                "dispatch": {},
                "last_mcp_error": err,
            })

        conn: Optional[MCPConnection] = None
        all_artifacts: List[Dict[str, Any]] = []
        call_audits: List[ToolCallAudit] = []

        try:
            conn = await MCPConnection.connect(transport_cfg)

            # Optional discovery
            try:
                disc = await conn.list_tools()
                logger.info("[MCP] Discovered %d tool(s): %s", len(disc), ", ".join(n for (n, _) in disc))
            except Exception:
                logger.debug("[MCP] list_tools failed (non-fatal).")

            # Initial call
            logger.info("[MCP] Invoking tool: %s args=%s", tool_name, json.dumps(tool_args, ensure_ascii=False))
            call_started = datetime.now(timezone.utc)
            raw_result: Any = None
            call_status: Literal["ok", "failed"] = "ok"
            validation_errors: List[str] = []

            try:
                raw_result = await conn.invoke_tool(tool_name, tool_args)
                logger.info("[MCP] Raw response from '%s' (trimmed): %s", tool_name, _json_sample(raw_result))
            except Exception as tool_err:
                call_status = "failed"
                msg = f"{type(tool_err).__name__}: {tool_err}"
                validation_errors = [msg]
                raw_result = {"error": str(tool_err)}
                logger.error("[MCP] Tool '%s' failed: %s", tool_name, tool_err, exc_info=True)

            duration_ms = int((datetime.now(timezone.utc) - call_started).total_seconds() * 1000)
            call_audits.append(
                ToolCallAudit(
                    tool_name=tool_name,
                    tool_args_preview=tool_args,
                    raw_output_sample=_json_sample(raw_result, 800),
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
                    hint = "Upstream repo snapshot did not complete or produced a different paths_root. Ensure step s1 finishes and propagate its artifact.paths_root."

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
                return Command(goto="capability_executor", update={
                    "dispatch": {},
                    "last_mcp_error": "MCP tool error",
                })

            # Extract artifacts from first call
            extracted = _extract_artifacts_from_output(raw_result, artifacts_property)
            if extracted:
                logger.info("[MCP] Extracted %d artifact(s) from first call.", len(extracted))
                all_artifacts.extend(extracted)

            soft_deadline = started + timedelta(seconds=_cap_timeout(capability))
            max_attempts, interval_ms, jitter_ms = _polling_settings(capability)

            # Async polling
            job_id, status = _detect_async_job(raw_result)
            status_tool = _find_status_tool(capability)

            if job_id and status and status_tool:
                status_tool_name, status_tool_spec = status_tool
                id_arg_key = _pick_id_arg_key_for_status_tool(status_tool_spec) or "job_id"
                attempts = 0
                logger.info("[MCP] Detected async job: job_id=%s status=%s; will poll with '%s'.",
                            job_id, status, status_tool_name)

                while status in _RUNNING_STATES:
                    attempts += 1
                    if attempts > max_attempts or datetime.now(timezone.utc) >= soft_deadline:
                        raise TimeoutError(f"Polling timeout for id={job_id} (status='{status}')")

                    sleep_ms = interval_ms + random.randint(0, max(jitter_ms, 0))
                    await asyncio.sleep(sleep_ms / 1000.0)

                    poll_args = {id_arg_key: job_id}
                    logger.info("[MCP] Poll #%d: %s args=%s", attempts, status_tool_name, json.dumps(poll_args))
                    poll_started = datetime.now(timezone.utc)
                    poll_raw: Any = await conn.invoke_tool(status_tool_name, poll_args)
                    logger.info("[MCP] Poll response (trimmed): %s", _json_sample(poll_raw))
                    poll_dur_ms = int((datetime.now(timezone.utc) - poll_started).total_seconds() * 1000)

                    call_audits.append(
                        ToolCallAudit(
                            tool_name=status_tool_name,
                            tool_args_preview=poll_args,
                            raw_output_sample=_json_sample(poll_raw, 800),
                            validation_errors=[],
                            duration_ms=poll_dur_ms,
                            status="ok",
                        )
                    )
                    await runs_repo.append_tool_call_audit(run_uuid, step_id, call_audits[-1])

                    prog = _extract_progress(poll_raw)
                    if prog is not None:
                        logger.info("[MCP] Progress: %.1f%%", prog)

                    _, status2 = _detect_async_job(poll_raw)
                    if status2:
                        status = status2

                    extracted = _extract_artifacts_from_output(poll_raw, artifacts_property)
                    if extracted:
                        logger.info("[MCP] Extracted %d artifact(s) from poll.", len(extracted))
                        all_artifacts.extend(extracted)

                if status in _ERROR_STATES:
                    raise RuntimeError(f"MCP job failed (id={job_id}, status={status})")
                if status not in _DONE_STATES:
                    logger.warning("[MCP] Async job ended in unusual status: %s", status)
                logger.info("[MCP] Async job completed: id=%s status=%s (artifacts=%d)",
                            job_id, status, len(all_artifacts))

            # Pagination
            pages_fetched = 0
            if _supports_pagination(capability):
                next_cursor = _extract_next_cursor(raw_result)
                page_tool = status_tool[0] if job_id and status_tool else tool_name
                seen_cursors = set()
                last_fp: Optional[str] = None
                page_idx = 1
                while next_cursor:
                    if datetime.now(timezone.utc) >= soft_deadline:
                        raise TimeoutError(f"Pagination timeout; last cursor={next_cursor}")
                    if next_cursor in seen_cursors:
                        logger.warning("[MCP] Repeated cursor detected (%s); breaking pagination loop.", next_cursor)
                        break
                    seen_cursors.add(next_cursor)
                    if pages_fetched >= _MAX_PAGES:
                        logger.warning("[MCP] Page cap reached (%d); stopping pagination.", _MAX_PAGES)
                        break

                    page_args = dict(tool_args)
                    page_args["cursor"] = next_cursor
                    logger.info("[MCP] Page #%d: %s args=%s", page_idx + 1, page_tool, json.dumps(page_args, ensure_ascii=False))
                    pg_started = datetime.now(timezone.utc)
                    pg_raw = await conn.invoke_tool(page_tool, page_args)
                    logger.info("[MCP] Page response (trimmed): %s", _json_sample(pg_raw))
                    pg_dur_ms = int((datetime.now(timezone.utc) - pg_started).total_seconds() * 1000)

                    call_audits.append(
                        ToolCallAudit(
                            tool_name=page_tool,
                            tool_args_preview=page_args,
                            raw_output_sample=_json_sample(pg_raw, 800),
                            validation_errors=[],
                            duration_ms=pg_dur_ms,
                            status="ok",
                        )
                    )
                    await runs_repo.append_tool_call_audit(run_uuid, step_id, call_audits[-1])

                    extracted = _extract_artifacts_from_output(pg_raw, artifacts_property)
                    if extracted:
                        logger.info("[MCP] Extracted %d artifact(s) from page.", len(extracted))
                        all_artifacts.extend(extracted)

                    fp = json.dumps({"cursor": next_cursor, "artifacts": extracted[:3]}, ensure_ascii=False)
                    if fp == last_fp:
                        logger.warning("[MCP] Identical page fingerprint encountered; breaking pagination loop.")
                        break
                    last_fp = fp

                    next_cursor = _extract_next_cursor(pg_raw)
                    page_idx += 1
                    pages_fetched += 1

                logger.info("[MCP] Pagination finished: pages=%d artifacts_total=%d", pages_fetched, len(all_artifacts))

            # Finalize
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

            # Hand off to router with breadcrumb; DO NOT write current_step_id here
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
                        "pages_fetched": pages_fetched if _supports_pagination(capability) else 0,
                    },
                    "last_mcp_error": None,
                },
            )

        except Exception as e:
            tb = traceback.format_exc(limit=5)
            err_msg = f"MCP execution error: {e}"
            logger.error("[MCP] %s\n%s", err_msg, tb)

            await runs_repo.append_step_audit(
                run_uuid,
                StepAudit(
                    step_id=step_id,
                    capability_id=cap_id,
                    mode="mcp",
                    inputs_preview=inputs_preview,
                    calls=call_audits or [ToolCallAudit(
                        tool_name=tool_name,
                        tool_args_preview=tool_args,
                        raw_output_sample=(err_msg + " :: " + tb)[:800],
                        status="failed"
                    )],
                ),
            )
            await runs_repo.step_failed(run_uuid, step_id, error=err_msg)
            return Command(goto="capability_executor", update={
                "dispatch": {},
                "last_mcp_error": err_msg,
            })

        finally:
            try:
                if conn is not None:
                    await conn.aclose()
            except Exception:
                pass

    return _node