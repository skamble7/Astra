# services/conductor-service/app/agent/nodes/diagram_enrichment.py
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from uuid import UUID

from typing_extensions import Literal
from langgraph.types import Command

from app.db.run_repository import RunRepository
from app.models.run_models import StepAudit, ToolCallAudit
from app.agent.mcp.mcp_client import MCPConnection, MCPTransportConfig

logger = logging.getLogger("app.agent.nodes.diagram_enrichment")


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
    # concise, non-verbose transport snapshot (no secrets)
    logger.info(
        "[enrich] transport cap_id=%s kind=%s base=%s path=%s timeout_s=%s tls=%s",
        cap.get("id") or cap.get("name") or "<unknown-cap>",
        cfg.kind,
        (cfg.base_url or "").rstrip("/"),
        cfg.protocol_path,
        cfg.timeout_sec,
        cfg.verify_tls,
    )
    return cfg


def _artifact_kind_id(a: Dict[str, Any]) -> Optional[str]:
    for key in ("kind_id", "kind", "_kind", "artifact_kind", "type"):
        v = a.get(key)
        if isinstance(v, str) and v:
            return v
    return None


def _artifact_data(a: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    data = a.get("data")
    if isinstance(data, dict):
        return data
    wrapped_keys = {"kind", "kind_id", "schema_version", "identity", "diagrams", "narratives", "provenance"}
    if isinstance(a, dict) and not (wrapped_keys & set(a.keys())):
        return a
    return None


def _latest_schema_entry(kind_spec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(kind_spec, dict):
        return None
    latest = kind_spec.get("latest_schema_version")
    versions = kind_spec.get("schema_versions") or []
    if isinstance(latest, str):
        for sv in versions:
            if isinstance(sv, dict) and sv.get("version") == latest:
                return sv
    return versions[0] if versions and isinstance(versions[0], dict) else None


def _views_for_kind(kind_spec: Dict[str, Any]) -> List[str]:
    entry = _latest_schema_entry(kind_spec)
    recipes = (entry or {}).get("diagram_recipes") or []
    views: List[str] = []
    for r in recipes:
        view = (r or {}).get("view")
        if isinstance(view, str) and view and view not in views:
            views.append(view)
    return views or ["flowchart"]


def _select_artifacts_for_step(*, staged: List[Dict[str, Any]], step_id: Optional[str]) -> List[Dict[str, Any]]:
    """
    STRICT SCOPING: Only return artifacts produced in the current step.
    Never fall back to all staged artifacts; that caused cross-step leakage.
    """
    if not staged or not step_id:
        return []
    tagged = [a for a in staged if isinstance(a, dict) and a.get("produced_in_step_id") == step_id]
    return tagged


def _json_sample(val: Any, limit: int = 1000) -> str:
    try:
        s = val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)
    except Exception:
        s = "<unserializable>"
    return s[:limit] + ("…" if len(s) > limit else "")


def diagram_enrichment_node(*, runs_repo: RunRepository):
    async def _node(state: Dict[str, Any]) -> Command[Literal["capability_executor"]] | Dict[str, Any]:
        run = state["run"]
        run_uuid = UUID(run["run_id"])
        current_step_id = state.get("current_step_id")

        artifact_kinds: Dict[str, Any] = state.get("artifact_kinds") or {}
        staged: List[Dict[str, Any]] = state.get("staged_artifacts") or []

        agent_caps_map: Dict[str, Dict[str, Any]] = state.get("agent_capabilities_map") or {}
        mermaid_cap = agent_caps_map.get("cap.diagram.mermaid")

        # Early exits with explicit breadcrumbs
        if not mermaid_cap:
            note = "Agent capability 'cap.diagram.mermaid' not present; enrichment skipped."
            logger.info("[enrich] skip reason=no_capability step_id=%s", current_step_id)
            return Command(
                goto="capability_executor",
                update={
                    "last_enrichment_summary": {
                        "completed_step_id": current_step_id,
                        "artifacts_considered": 0,
                        "recipes_total": 0,
                        "diagrams_written": 0,
                        "diagrams_failed": 0,
                        "capability_detected": False,
                        "missing_kind_specs": [],
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "note": note,
                    },
                    "last_enrichment_error": None,
                },
            )

        artifacts = _select_artifacts_for_step(staged=staged, step_id=current_step_id)
        if not artifacts:
            note = "No staged artifacts for current step; enrichment skipped."
            logger.info("[enrich] skip reason=no_artifacts_for_step step_id=%s", current_step_id)
            return Command(
                goto="capability_executor",
                update={
                    "last_enrichment_summary": {
                        "completed_step_id": current_step_id,
                        "artifacts_considered": 0,
                        "recipes_total": 0,
                        "diagrams_written": 0,
                        "diagrams_failed": 0,
                        "capability_detected": True,
                        "missing_kind_specs": [],
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "note": note,
                    },
                    "last_enrichment_error": None,
                },
            )

        # Prepare transport/connection
        try:
            transport_cfg = _transport_from_capability(mermaid_cap)
        except Exception as e:
            err = f"invalid MCP transport for 'cap.diagram.mermaid': {e}"
            logger.error("[enrich] %s", err)
            return Command(
                goto="capability_executor",
                update={
                    "last_enrichment_summary": {
                        "completed_step_id": current_step_id,
                        "artifacts_considered": len(artifacts),
                        "recipes_total": 0,
                        "diagrams_written": 0,
                        "diagrams_failed": 0,
                        "capability_detected": True,
                        "missing_kind_specs": [],
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "note": "transport invalid; enrichment skipped",
                    },
                    "last_enrichment_error": err,
                },
            )

        tool_name = "diagram.mermaid.generate"

        written = 0
        failed = 0
        recipes_total = 0
        missing_kinds: Set[str] = set()
        step_audit_calls: List[ToolCallAudit] = []

        conn: Optional[MCPConnection] = None
        try:
            conn = await MCPConnection.connect(transport_cfg)

            # Discovery snapshot
            try:
                disc = await conn.list_tools()
                tool_list = [n for (n, _) in disc]
                logger.info("[enrich] tools_discovered count=%d names=%s", len(tool_list), ", ".join(tool_list))
            except Exception:
                logger.info("[enrich] tools_discovered failed (non-fatal)")

            updated_staged = list(staged)

            for idx, art in enumerate(artifacts):
                kind_id = _artifact_kind_id(art)
                kind_spec = artifact_kinds.get(kind_id) if kind_id else None
                if kind_id and not kind_spec:
                    missing_kinds.add(kind_id)

                views = _views_for_kind(kind_spec) if kind_spec else ["flowchart"]
                recipes_total += len(views)

                data_obj = _artifact_data(art)
                if not isinstance(data_obj, dict):
                    failed += len(views)
                    logger.info("[enrich] skip idx=%d reason=no_data kind=%s", idx, kind_id)
                    continue

                args = {"artifact": data_obj, "views": views}
                # Input snapshot for this MCP call (trimmed)
                logger.info(
                    "[enrich] call tool=%s idx=%d kind=%s views=%s arg_keys=%d",
                    tool_name, idx, kind_id, ",".join(views), len(args.keys())
                )
                logger.debug("[enrich] call_args_sample idx=%d %s", idx, _json_sample(args, 800))

                call_started = datetime.now(timezone.utc)
                call_status: Literal["ok", "failed"] = "ok"
                raw_result: Any = None
                validation_errors: List[str] = []

                try:
                    raw_result = await conn.invoke_tool(tool_name, args)
                    # Output snapshot (trimmed)
                    logger.info("[enrich] result tool=%s idx=%d (sample)", tool_name, idx)
                    logger.debug("[enrich] result_sample idx=%d %s", idx, _json_sample(raw_result, 800))
                except Exception as tool_err:
                    call_status = "failed"
                    msg = f"{type(tool_err).__name__}: {tool_err}"
                    validation_errors = [msg]
                    raw_result = {"error": str(tool_err)}
                    logger.error("[enrich] tool_error tool=%s idx=%d msg=%s", tool_name, idx, msg)

                duration_ms = int((datetime.now(timezone.utc) - call_started).total_seconds() * 1000)
                call_audit = ToolCallAudit(
                    tool_name=tool_name,
                    tool_args_preview=args,
                    raw_output_sample=_json_sample(raw_result, 800),
                    validation_errors=validation_errors,
                    duration_ms=duration_ms,
                    status=call_status,
                )
                step_audit_calls.append(call_audit)
                await runs_repo.append_tool_call_audit(run_uuid, current_step_id or "<unknown-step>", call_audit)

                if call_status == "failed":
                    failed += len(views)
                    continue

                try:
                    payload = raw_result if isinstance(raw_result, dict) else json.loads(str(raw_result))
                except Exception:
                    payload = {}

                diagrams = payload.get("diagrams") if isinstance(payload, dict) else None
                if not isinstance(diagrams, list):
                    failed += len(views)
                    continue

                attached = 0
                attach_list = art.get("diagrams") if isinstance(art.get("diagrams"), list) else []
                if not isinstance(attach_list, list):
                    attach_list = []

                for d in diagrams:
                    if not isinstance(d, dict):
                        continue
                    view = d.get("view")
                    lang = d.get("language")
                    instr = d.get("instructions")
                    if isinstance(view, str) and isinstance(lang, str) and isinstance(instr, str) and instr.strip():
                        attach_list.append({
                            "id": f"auto:{view}",
                            "view": view,
                            "language": lang,
                            "instructions": instr,
                            "renderer_hints": d.get("renderer_hints") or {},
                            "provenance": {
                                "capability_id": mermaid_cap.get("id"),
                                "tool_name": tool_name,
                                "ts": datetime.now(timezone.utc).isoformat(),
                            },
                        })
                        attached += 1

                if attached > 0:
                    written += attached
                    try:
                        original_idx = updated_staged.index(art)
                        new_art = dict(updated_staged[original_idx])
                        new_art["diagrams"] = attach_list
                        updated_staged[original_idx] = new_art
                    except ValueError:
                        na = dict(art)
                        na["diagrams"] = attach_list
                        updated_staged.append(na)
                else:
                    failed += len(views)

            # Final audit + summary
            await runs_repo.append_step_audit(
                run_uuid,
                StepAudit(
                    step_id=current_step_id or "<unknown-step>",
                    capability_id=mermaid_cap.get("id") or "cap.diagram.mermaid",
                    mode="mcp",
                    inputs_preview={"phase": "diagram-enrichment", "tool_name": tool_name},
                    calls=step_audit_calls,
                    notes_md=None,
                ),
            )

            logger.info(
                "[enrich] handoff step_id=%s artifacts=%d recipes=%d written=%d failed=%d missing_kinds=%d",
                current_step_id, len(artifacts), recipes_total, written, failed, len(missing_kinds)
            )

            return Command(
                goto="capability_executor",
                update={
                    "staged_artifacts": updated_staged,
                    "last_enrichment_summary": {
                        "completed_step_id": current_step_id,
                        "artifacts_considered": len(artifacts),
                        "recipes_total": recipes_total,
                        "diagrams_written": written,
                        "diagrams_failed": failed,
                        "capability_detected": True,
                        "missing_kind_specs": sorted(list(missing_kinds)) if missing_kinds else [],
                        "ts": datetime.now(timezone.utc).isoformat(),
                    },
                    "last_enrichment_error": None if failed == 0 else "Some diagrams failed to generate",
                },
            )

        except Exception as e:
            err_msg = f"diagram_enrichment MCP execution error: {e}"
            logger.error("[enrich] error step_id=%s msg=%s", current_step_id, err_msg)
            return Command(
                goto="capability_executor",
                update={
                    "last_enrichment_summary": {
                        "completed_step_id": current_step_id,
                        "artifacts_considered": len(artifacts),
                        "recipes_total": recipes_total,
                        "diagrams_written": 0,
                        "diagrams_failed": recipes_total,
                        "capability_detected": True,
                        "missing_kind_specs": sorted(list(missing_kinds)) if missing_kinds else [],
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "note": "unexpected exception; enrichment skipped",
                    },
                    "last_enrichment_error": err_msg,
                },
            )
        finally:
            try:
                if conn is not None:
                    await conn.aclose()
            except Exception:
                pass

    return _node