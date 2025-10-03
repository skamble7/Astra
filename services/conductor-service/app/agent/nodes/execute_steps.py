# services/conductor-service/app/agent/nodes/execute_steps.py
from __future__ import annotations

import asyncio
import json
import logging
import re
import inspect
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Callable
from uuid import UUID

from app.clients.artifact_service import ArtifactServiceClient  # noqa: F401 (placeholder if/when wired)
from app.db.mongodb import get_client
from app.db.run_repository import RunRepository
from app.events.rabbit import get_bus
from app.llm.factory import get_agent_llm
from app.models.run_models import ArtifactEnvelope, ArtifactProvenance, ToolCallAudit  # noqa: F401
from app.config import settings

logger = logging.getLogger("app.agent.nodes.execute")


# ──────────────────────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────────────────────

def _json_preview(obj: Any, limit: int = 1200) -> Any:
    try:
        s = json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        s = str(obj)
    return s if len(s) <= limit else s[:limit] + f"...(+{len(s)-limit}B)"


def _block_text(block: Any) -> Optional[str]:
    if isinstance(block, dict):
        if block.get("type") == "text":
            return str(block.get("text", "")).strip()
        return None
    if getattr(block, "type", None) == "text":
        return str(getattr(block, "text", "")).strip()
    return None


def _extract_job_id(pages: List[Dict[str, Any]]) -> Optional[str]:
    for pg in pages:
        datum = (pg or {}).get("data") or {}
        structured = datum.get("structured")
        if isinstance(structured, dict):
            for key in ("job_id", "id", "jobId"):
                if structured.get(key):
                    return str(structured[key])

        for block in (datum.get("content") or []):
            txt = _block_text(block)
            if not txt:
                continue
            # try JSON parse
            try:
                obj = json.loads(txt)
                if isinstance(obj, dict):
                    for key in ("job_id", "id", "jobId"):
                        if obj.get(key):
                            return str(obj[key])
                elif isinstance(obj, list):
                    for item in obj:
                        if isinstance(item, dict):
                            for key in ("job_id", "id", "jobId"):
                                if item.get(key):
                                    return str(item[key])
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


# ──────────────────────────────────────────────────────────────────────────────
# MCP client builders (LangGraph first, official SDK fallback) – inline
# ──────────────────────────────────────────────────────────────────────────────

class _MCPAdapterProto:
    async def discovery(self) -> Dict[str, Any]: ...
    async def call_tool(self, tool_name: str, args: Dict[str, Any], timeout_sec: int) -> Dict[str, Any]: ...
    async def close(self) -> None: ...


def _format_result_from_sdk(result: Any) -> Dict[str, Any]:
    """Normalize official SDK CallToolResult -> {pages:[{data:{content,structured}}]}"""
    structured = getattr(result, "structuredContent", None)
    raw_content = getattr(result, "content", None) or []
    content = []
    for b in raw_content:
        t = getattr(b, "type", None)
        if t == "text":
            content.append({"type": "text", "text": getattr(b, "text", "")})
        elif t == "image":
            content.append({"type": "image", "mimeType": getattr(b, "mimeType", None), "data": getattr(b, "data", None)})
        elif isinstance(b, dict):
            content.append(b)
        else:
            try:
                d = dict(getattr(b, "__dict__", {}))
                d.setdefault("type", str(t) if t else "unknown")
                content.append(d)
            except Exception:
                content.append({"type": str(t) if t else "unknown"})
    pages = [{"data": {"content": content, "structured": structured}, "cursor": None}]
    return {"pages": pages, "stream": None, "metrics": {}}


async def _build_mcp_client_from_capability(exec_cfg: Dict[str, Any]) -> _MCPAdapterProto:
    """
    Build a per-step MCP client from the capability execution config.
    Prefers the LangGraph MCP client. Falls back to official SDK streamable HTTP.
    """
    transport = dict(exec_cfg.get("transport") or {})
    kind = (transport.get("kind") or "").lower()
    if kind != "http":
        raise RuntimeError(f"Unsupported MCP transport kind: {kind!r}")

    base_url = (transport.get("base_url") or "").rstrip("/")
    mcp_path = transport.get("mcp_path") or transport.get("stream_path") or "/mcp"
    headers = dict(transport.get("headers") or {})
    timeout_init = int(transport.get("init_timeout_sec") or transport.get("timeout_sec") or 30)
    verify_tls = bool(transport.get("verify_tls", True))

    # 1) Try LangGraph MCP
    try:
        try:
            # Newer import path
            from langgraph.mcp import client as lg_client
        except Exception:
            # Older nested path
            from langgraph.mcp.client import client as lg_client  # type: ignore

        logger.info("Connecting MCP via LangGraph client: %s%s", base_url, mcp_path)

        # LangGraph client API: connect_http(base_url, path="/mcp", headers=..., timeout=...)
        # We keep kwargs narrow for compatibility across versions.
        conn = await lg_client.connect_http(base_url=base_url, path=mcp_path, headers=headers, timeout=timeout_init)

        class _LGAdapter(_MCPAdapterProto):
            def __init__(self, c) -> None:
                self._c = c

            async def discovery(self) -> Dict[str, Any]:
                # Normalize to {tools: [str], resources: [...], prompts: [...]}
                try:
                    tools = await self._c.list_tools()
                except Exception:
                    tools = []
                try:
                    resources = await self._c.list_resources()
                except Exception:
                    resources = []
                try:
                    prompts = await self._c.list_prompts()
                except Exception:
                    prompts = []
                return {"tools": [getattr(t, "name", t) for t in tools or []], "resources": resources or [], "prompts": prompts or []}

            async def call_tool(self, tool_name: str, args: Dict[str, Any], timeout_sec: int) -> Dict[str, Any]:
                async def _call():
                    return await self._c.call_tool(tool_name, arguments=args)
                res = await asyncio.wait_for(_call(), timeout=timeout_sec)
                # LangGraph client already returns a dict-like `{"content":[...], "structured":...}`?
                # Normalize defensively:
                if isinstance(res, dict) and "pages" in res:
                    return res  # already normalized by lg client
                # best-effort normalization
                content = res.get("content") if isinstance(res, dict) else None
                structured = res.get("structured") if isinstance(res, dict) else None
                pages = [{"data": {"content": content or [], "structured": structured}, "cursor": None}]
                return {"pages": pages, "stream": None, "metrics": {}}

            async def close(self) -> None:
                with contextlib.suppress(Exception):
                    await self._c.close()

        return _LGAdapter(conn)

    except Exception as e:
        logger.info("LangGraph MCP connection failed (%s). Falling back to official MCP SDK…", e)

    # 2) Fallback: official MCP (streamable HTTP). Avoid passing unknown kwargs (e.g., verify_tls) to older versions.
    from mcp.client.session import ClientSession  # type: ignore
    try:
        from mcp.client.streamable_http import streamablehttp_client  # type: ignore
    except Exception:
        streamablehttp_client = None  # type: ignore

    if not streamablehttp_client:
        raise RuntimeError("Official MCP streamable HTTP client not available")

    # signature-safe kwargs
    call_kwargs = {"headers": headers}
    try:
        sig = inspect.signature(streamablehttp_client)
        # only pass verify_tls if supported by the installed version
        if "verify_tls" in sig.parameters:
            call_kwargs["verify_tls"] = verify_tls
    except Exception:
        pass

    stream_url = f"{base_url}{mcp_path}"
    logger.info("Connecting MCP via official SDK (streamable): %s", stream_url)

    ctx = streamablehttp_client(stream_url, **call_kwargs)  # type: ignore[arg-type]
    read = write = session = None

    # enter context now and return an adapter that uses this session
    read, write, _get_session_id = await ctx.__aenter__()  # type: ignore[assignment,union-attr]
    session = ClientSession(read, write)
    # guard initialize with timeout
    await asyncio.wait_for(session.initialize(), timeout=timeout_init)

    class _SDKAdapter(_MCPAdapterProto):
        def __init__(self, ctx, sess) -> None:
            self._ctx = ctx
            self._session = sess

        async def discovery(self) -> Dict[str, Any]:
            tools = await self._session.list_tools()
            try:
                resources = await self._session.list_resources()
            except Exception:
                resources = []
            try:
                prompts = await self._session.list_prompts()
            except Exception:
                prompts = []
            return {"tools": [t.name for t in (tools or [])], "resources": resources or [], "prompts": prompts or []}

        async def call_tool(self, tool_name: str, args: Dict[str, Any], timeout_sec: int) -> Dict[str, Any]:
            async def _call():
                return await self._session.call_tool(tool_name, arguments=args)
            res = await asyncio.wait_for(_call(), timeout=timeout_sec)
            return _format_result_from_sdk(res)

        async def close(self) -> None:
            try:
                await self._session.shutdown()
            except Exception:
                pass
            try:
                await self._ctx.__aexit__(None, None, None)  # type: ignore[union-attr]
            except Exception:
                pass

    return _SDKAdapter(ctx, session)


# ──────────────────────────────────────────────────────────────────────────────
# Output normalization
# ──────────────────────────────────────────────────────────────────────────────

async def _normalize_tool_output_to_artifacts(
    *,
    pages: List[Dict[str, Any]],
    capability: Dict[str, Any],
    run_meta: Dict[str, Any],
) -> List[ArtifactEnvelope]:
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
            txt = _block_text(block)
            if not txt:
                continue
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


# ──────────────────────────────────────────────────────────────────────────────
# LLM arg synthesis
# ──────────────────────────────────────────────────────────────────────────────

async def _synthesize_tool_args_with_llM(
    *,
    step: Dict[str, Any],
    capability: Dict[str, Any],
    inputs: Dict[str, Any],
) -> Dict[str, Any]:
    llm = get_agent_llm()
    tool_calls = (capability.get("execution", {}).get("tool_calls") or [])
    if not tool_calls:
        args = step.get("params") or {}
        logger.debug("LLM synthesis skipped (no tool_calls). Using step.params=%s", _json_preview(args))
        return args

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
        logger.warning("LLM tool-args synthesis failed; using step.params")
        return step.get("params") or {}


# ──────────────────────────────────────────────────────────────────────────────
# Main node
# ──────────────────────────────────────────────────────────────────────────────

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

            mode = exec_cfg.get("mode")
            if mode == "mcp":
                # Build MCP client (LangGraph first, then official)
                mcp_client = await _build_mcp_client_from_capability(exec_cfg)

                # Discovery + logging (requested)
                discovery = await mcp_client.discovery()
                discovered_tools = [t for t in (discovery.get("tools") or [])]
                logger.info("MCP discovery for %s: tools=%s (resources=%s, prompts=%s)",
                            cap_id,
                            discovered_tools,
                            len(discovery.get("resources") or []),
                            len(discovery.get("prompts") or []))

                # build args (LLM-assisted)
                args = await _synthesize_tool_args_with_llM(step=step, capability=capability, inputs=inputs)
                logger.info("Prepared tool args for %s: %s", cap_id, _json_preview(args))

                tool_calls = exec_cfg.get("tool_calls") or []
                if not tool_calls:
                    raise RuntimeError(f"Capability {cap_id} has no tool_calls")

                def _find_tool(name_substr: str) -> Optional[str]:
                    for t in discovered_tools:
                        if name_substr in t:
                            return t
                    for t in [tc.get("tool") for tc in tool_calls if tc.get("tool")]:
                        if name_substr in t:
                            return t
                    return None

                start_tool = _find_tool(".start") or _find_tool("snapshot.start") or (tool_calls[0]["tool"] if tool_calls else None)
                status_tool = _find_tool(".status") or _find_tool("snapshot.status")

                # Timeouts per tool spec, fallback to transport timeout
                def _timeout_for(tool_name: str) -> int:
                    for tc in tool_calls:
                        if tc.get("tool") == tool_name:
                            return int(tc.get("timeout_sec", exec_cfg.get("transport", {}).get("timeout_sec", 120)))
                    return int(exec_cfg.get("transport", {}).get("timeout_sec", 120))

                pages_accum: List[Dict[str, Any]] = []

                # 1) call start
                if not start_tool:
                    raise RuntimeError(f"Could not resolve start tool for capability {cap_id}")
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

                    logger.info(
                        "Polling status via tool=%s (max=%s, interval=%ss)",
                        status_tool,
                        max_polls,
                        poll_delay,
                    )
                    for i in range(max_polls):
                        res = await mcp_client.call_tool(status_tool, poll_args, timeout_sec=_timeout_for(status_tool))
                        pages = res.get("pages") or []
                        pages_accum.extend(pages)

                        # Heuristic terminal detection
                        terminal = False
                        for pg in pages:
                            st = (((pg or {}).get("data") or {}).get("structured") or {}) or {}
                            if isinstance(st, dict):
                                status_val = str(st.get("status") or st.get("state") or "").lower()
                                if status_val in {"done", "success", "completed", "complete", "ok"}:
                                    terminal = True
                                elif status_val in {"failed", "error"}:
                                    terminal = True
                        logger.info("Poll %d/%d -> terminal=%s", i + 1, max_polls, terminal)
                        if terminal:
                            break
                        await asyncio.sleep(poll_delay)

                # Close per-step client
                with contextlib.suppress(Exception):
                    await mcp_client.close()

                call_audit.tool_name = start_tool
                call_audit.tool_args_preview = (args if len(_json_preview(args)) < 1200 else {"_size": len(str(args))})

                produced_artifacts = await _normalize_tool_output_to_artifacts(
                    pages=pages_accum,
                    capability=capability,
                    run_meta={"run_id": state["run"]["run_id"], "step_id": step_id, "capability_id": cap_id},
                )

            elif mode == "llm":
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
                raise RuntimeError(f"Unsupported execution mode for capability {cap_id}: {mode}")

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