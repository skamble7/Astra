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

from conductor_core.protocols.repositories import RunRepositoryProtocol as RunRepository
from conductor_core.models.run_models import StepAudit, ToolCallAudit
from conductor_core.mcp.mcp_client import MCPConnection, MCPTransportConfig
from conductor_core.mcp.json_utils import try_parse_json, get_by_dotted_path

logger = logging.getLogger("conductor_core.nodes.mcp_execution")

_ASYNC_STATUS_SUFFIXES = (".status", ".check", ".poll", ".progress")
_JOB_ID_KEYS = ("job_id", "operation_id", "task_id", "id")

_RUNNING_STATES = {"queued", "running", "in_progress", "pending"}
_DONE_STATES = {"done", "completed", "succeeded", "success"}
_ERROR_STATES = {"error", "failed", "failure"}

_MAX_PAGES = 1000


# -----------------------------
# Canonical payload unwrapping
# -----------------------------
def _unwrap_payload(raw: Any) -> Any:
    """
    Standardize MCP tool results into a JSON-like Python object.

    Supports FastMCP / streamable-http style:
      raw_result == [ { "type": "text", "text": "{...json...}" }, ... ]

    - If the text content is valid JSON (dict or list), unwrap and return it.
    - If the text content is plain text (not JSON), return the text string directly
      so callers can do schema-driven mapping.
    """
    parsed = try_parse_json(raw)

    # FastMCP content list: [{type, text, ...}, ...]
    if isinstance(parsed, list) and parsed and all(isinstance(x, dict) and "type" in x for x in parsed):
        text_chunks: List[str] = [
            x.get("text") for x in parsed
            if isinstance(x.get("text"), str)
        ]
        joined = "\n".join(text_chunks).strip()
        if joined:
            inner = try_parse_json(joined)
            if isinstance(inner, (dict, list)):
                logger.info(
                    "[mcp] fastmcp_json_unwrapped items=%d text_len=%d",
                    len(parsed),
                    len(joined),
                )
                return inner
            # Plain text content — return the text string directly
            logger.info(
                "[mcp] fastmcp_text_content items=%d text_len=%d",
                len(parsed),
                len(joined),
            )
            return joined
        return parsed

    return parsed




# -----------------------------
# Capability helpers
# -----------------------------
def _exec_block(cap: Dict[str, Any]) -> Dict[str, Any]:
    return (cap.get("execution") or {})


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
        "[mcp] transport cap_id=%s kind=%s base=%s path=%s timeout_s=%s tls=%s",
        cap.get("id") or cap.get("name") or "<unknown-cap>",
        cfg.kind,
        (cfg.base_url or "").rstrip("/"),
        cfg.protocol_path,
        cfg.timeout_sec,
        cfg.verify_tls,
    )
    return cfg



def _find_status_tool_from_discovered(discovered: Dict[str, Any]) -> Optional[Tuple[str, Dict[str, Any]]]:
    """
    Finds a status/poll tool for async jobs from the discovered tools cache.
    discovered: {tool_name: json_schema_dict}  (from state["discovered_tools"][cap_id])

    Prefers tools whose name ends with a status suffix AND whose schema requires a job-id arg.
    Falls back to any tool requiring a job-id arg.
    """
    def _requires_id(schema: Dict[str, Any]) -> bool:
        props = (schema.get("properties") or {})
        required = set(schema.get("required") or [])
        return any(k in props and k in required for k in _JOB_ID_KEYS)

    # First pass: name-suffix + id requirement
    for name, schema in discovered.items():
        if name.lower().endswith(_ASYNC_STATUS_SUFFIXES) and _requires_id(schema):
            return name, schema
    # Second pass: just id requirement
    for name, schema in discovered.items():
        if _requires_id(schema):
            return name, schema
    return None


# -----------------------------
# Contract metadata extraction
# -----------------------------
def _detect_async_job(payload: Any) -> Tuple[Optional[str], Optional[str]]:
    """
    Contract: async tools return { job_id, status, ... } (outside artifacts).
    """
    if not isinstance(payload, dict):
        return None, None

    job_id = None
    for k in _JOB_ID_KEYS:
        v = payload.get(k)
        if isinstance(v, str) and v:
            job_id = v
            break

    status = payload.get("status")
    if isinstance(job_id, str) and isinstance(status, str) and status:
        return job_id, status.lower()

    return None, None


def _extract_next_cursor(payload: Any) -> Optional[str]:
    """
    Contract: pagination returns next_cursor (outside artifacts).
    """
    if not isinstance(payload, dict):
        return None

    nxt = payload.get("next_cursor")
    if isinstance(nxt, str) and nxt.strip():
        return nxt.strip()

    # tolerant fallbacks (optional)
    for key in ("cursor.next", "nextPageToken", "page.next"):
        v = get_by_dotted_path(payload, key)
        if isinstance(v, str) and v.strip():
            return v.strip()

    return None


def _extract_progress(payload: Any) -> Optional[float]:
    """
    Contract: async tools may return progress (outside artifacts).
    """
    if not isinstance(payload, dict):
        return None

    prog = payload.get("progress")
    if prog is not None:
        try:
            return float(prog)
        except Exception:
            return None

    # tolerant fallbacks (optional)
    for key in ("data.progress", "result.progress", "meta.progress_percent"):
        v = get_by_dotted_path(payload, key)
        if v is not None:
            try:
                return float(v)
            except Exception:
                pass
    return None


def _polling_settings(cap: Dict[str, Any]) -> Tuple[int, int, int]:
    ex = _exec_block(cap)
    p = (ex.get("polling") or {})
    return int(p.get("max_attempts", 120)), int(p.get("interval_ms", 1000)), int(p.get("jitter_ms", 250))


def _cap_timeout(cap: Dict[str, Any]) -> int:
    ts = _exec_block(cap).get("transport", {}).get("timeout_sec")
    return int(ts or 120)


def _json_sample(val: Any, limit: int = 800) -> str:
    try:
        s = val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)
    except Exception:
        s = "<unserializable>"
    return s[:limit] + ("…" if len(s) > limit else "")


def _pick_id_arg_key_for_status_tool(schema: Dict[str, Any]) -> Optional[str]:
    """schema is the tool's JSON Schema dict (plain, not wrapped in args_schema)."""
    props = (schema.get("properties") or {})
    required = set(schema.get("required") or [])
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


def _supports_pagination_by_contract(payload: Any) -> bool:
    """
    Contract-driven pagination:
      if payload contains next_cursor at any point, we paginate.
    """
    return _extract_next_cursor(payload) is not None


def _find_text_field(kind_spec: Optional[Dict[str, Any]]) -> Optional[str]:
    """
    Find the single required string property in the kind's JSON schema.
    Used to auto-map plain text MCP responses to the correct schema field.
    Returns None if the schema has zero or more than one required string property.
    """
    schema_versions = (kind_spec or {}).get("schema_versions") or []
    if not schema_versions:
        return None
    json_schema = (schema_versions[0] or {}).get("json_schema") or {}
    props = json_schema.get("properties") or {}
    required = set(json_schema.get("required") or [])
    string_fields = [
        k for k, v in props.items()
        if isinstance(v, dict) and v.get("type") == "string" and k in required
    ]
    return string_fields[0] if len(string_fields) == 1 else None


def _extract_artifacts_for_kind(
    payload: Any,
    produces_kind: Optional[str],
    kind_spec: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Wrap MCP tool output as Astra artifacts using the capability's produces_kind.

    The MCP server must return data conforming to the registered kind's JSON schema.
    Astra's kind_id and artifact terminology must never appear in MCP server responses.
    Validation against the schema happens downstream in persist_run.

    Supported payload shapes:
    - dict        → one artifact: {"kind_id": produces_kind, "data": payload}
    - list[dict]  → one artifact per item (all same kind)
    - str         → plain text; schema-driven mapping to the single required string field
    - list[str]   → same text mapping applied to each string item
    """
    if not produces_kind:
        return []

    def _wrap_text(text: str) -> Optional[Dict[str, Any]]:
        text_field = _find_text_field(kind_spec)
        if not text_field:
            logger.warning(
                "[mcp] plain_text_no_mapping produces_kind=%s; kind schema has no single required string field",
                produces_kind,
            )
            return None
        return {"kind_id": produces_kind, "data": {text_field: text}}

    if isinstance(payload, str):
        artifact = _wrap_text(payload)
        if artifact:
            logger.info("[mcp] plain_text_mapped produces_kind=%s field=%s text_len=%d", produces_kind, _find_text_field(kind_spec), len(payload))
        return [artifact] if artifact else []

    if isinstance(payload, list):
        results: List[Dict[str, Any]] = []
        for item in payload:
            if isinstance(item, dict):
                results.append({"kind_id": produces_kind, "data": item})
            elif isinstance(item, str):
                artifact = _wrap_text(item)
                if artifact:
                    results.append(artifact)
        return results

    if isinstance(payload, dict):
        return [{"kind_id": produces_kind, "data": payload}]

    return []


# -----------------------------
# Node
# -----------------------------
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
        produces_kinds: List[str] = capability.get("produces_kinds") or []
        produces_kind: Optional[str] = produces_kinds[0] if produces_kinds else None
        kind_spec: Optional[Dict[str, Any]] = (state.get("artifact_kinds") or {}).get(produces_kind) if produces_kind else None

        logger.info(
            "[mcp] start step_id=%s cap_id=%s tool=%s args_keys=%d produces_kind=%s",
            step_id,
            cap_id,
            tool_name or "<missing>",
            len(tool_args.keys()),
            produces_kind or "none",
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

            soft_deadline = started + timedelta(seconds=_cap_timeout(capability))
            max_attempts, interval_ms, jitter_ms = _polling_settings(capability)

            # 1) Initial call
            call_started = datetime.now(timezone.utc)
            raw_result: Any = None
            call_status: Literal["ok", "failed"] = "ok"
            validation_errors: List[str] = []

            try:
                raw_result = await conn.invoke_tool(tool_name, tool_args)
                logger.info(
                    "[mcp] raw_result step_id=%s cap_id=%s tool=%s type=%s sample=%s",
                    step_id, cap_id, tool_name, type(raw_result).__name__, _json_sample(raw_result),
                )
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

            # Canonical payload
            payload = _unwrap_payload(raw_result)

            # Extract artifacts: first try structured keys, then fall back to
            # produces_kind-driven wrapping (the MCP server output IS the artifact data).
            extracted = _extract_artifacts_for_kind(payload, produces_kind, kind_spec)
            logger.info(
                "[mcp] extracted_initial step_id=%s cap_id=%s tool=%s produces_kind=%s count=%d",
                step_id, cap_id, tool_name, produces_kind or "none", len(extracted)
            )
            if extracted:
                all_artifacts.extend(extracted)

            # 2) Async polling (contract-based)
            job_id, status = _detect_async_job(payload)
            cap_discovered = (state.get("discovered_tools") or {}).get(cap_id) or {}
            status_tool = _find_status_tool_from_discovered(cap_discovered)
            attempts = 0

            if job_id and status and status_tool:
                status_tool_name, status_schema = status_tool
                id_arg_key = _pick_id_arg_key_for_status_tool(status_schema) or "job_id"
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

                    poll_payload = _unwrap_payload(poll_raw)

                    prog = _extract_progress(poll_payload)
                    if prog is not None and attempts % 5 == 0:
                        logger.info("[mcp] progress job_id=%s attempts=%d progress=%.1f%%", job_id, attempts, prog)

                    _, status2 = _detect_async_job(poll_payload)
                    if status2:
                        status = status2

                    extracted_poll = _extract_artifacts_for_kind(poll_payload, produces_kind, kind_spec)
                    if extracted_poll:
                        logger.info(
                            "[mcp] extracted_poll step_id=%s cap_id=%s tool=%s count=%d",
                            step_id, cap_id, status_tool_name, len(extracted_poll)
                        )
                        all_artifacts.extend(extracted_poll)

                    # Important: keep latest payload for pagination after async completes
                    payload = poll_payload

                if status in _ERROR_STATES:
                    raise RuntimeError(f"MCP job failed (id={job_id}, status={status})")

                logger.info(
                    "[mcp] async_complete job_id=%s status=%s attempts=%d artifacts_total=%d",
                    job_id, status, attempts, len(all_artifacts)
                )

            # 3) Pagination (contract-based: next_cursor outside artifacts)
            pages_fetched = 0
            next_cursor = _extract_next_cursor(payload)

            if next_cursor:
                logger.info("[mcp] pagination_start first_cursor=%s", next_cursor)

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
                pg_raw = await conn.invoke_tool(tool_name, page_args)
                pg_dur_ms = int((datetime.now(timezone.utc) - pg_started).total_seconds() * 1000)

                call_audits.append(
                    ToolCallAudit(
                        tool_name=tool_name,
                        tool_args_preview=page_args,
                        raw_output_sample=_json_sample(pg_raw),
                        validation_errors=[],
                        duration_ms=pg_dur_ms,
                        status="ok",
                    )
                )
                await runs_repo.append_tool_call_audit(run_uuid, step_id, call_audits[-1])

                pg_payload = _unwrap_payload(pg_raw)
                extracted_page = _extract_artifacts_for_kind(pg_payload, produces_kind, kind_spec)

                if extracted_page:
                    logger.info(
                        "[mcp] extracted_page step_id=%s cap_id=%s tool=%s page=%d count=%d",
                        step_id, cap_id, tool_name, pages_fetched + 1, len(extracted_page)
                    )
                    all_artifacts.extend(extracted_page)

                next_cursor = _extract_next_cursor(pg_payload)
                pages_fetched += 1

            logger.info("[mcp] pagination_done pages=%d artifacts_total=%d", pages_fetched, len(all_artifacts))

            # 4) Finalize + DB audits
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

            # Annotate artifacts with step_id + normalize kind_id
            annotated: List[Dict[str, Any]] = []
            for a in all_artifacts:
                na = dict(a)
                na.setdefault("produced_in_step_id", step_id)
                if "kind_id" not in na:
                    if isinstance(na.get("kind"), str):
                        na["kind_id"] = na["kind"]
                    elif isinstance(na.get("_kind"), str):
                        na["kind_id"] = na["_kind"]
                    elif isinstance(na.get("artifact_kind"), str):
                        na["kind_id"] = na["artifact_kind"]
                annotated.append(na)

            prev_staged = state.get("staged_artifacts") or []
            new_staged = prev_staged + annotated

            logger.info(
                "[mcp] handoff step_id=%s cap_id=%s tool=%s calls=%d artifacts=%d pages=%d duration_ms=%d",
                step_id, cap_id, tool_name, len(call_audits), len(annotated), pages_fetched, duration_ms_total
            )

            return Command(
                goto="capability_executor",
                update={
                    "dispatch": {},
                    "staged_artifacts": new_staged,
                    "last_mcp_summary": {
                        "tool_calls": [
                            {"name": c.tool_name, "status": c.status, "duration_ms": c.duration_ms}
                            for c in call_audits
                        ],
                        "artifact_count": len(annotated),
                        "completed_step_id": step_id,
                        "pages_fetched": pages_fetched,
                        "async_job_id": job_id,
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
