# conductor_core/mcp/mcp_client.py
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, cast

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger("conductor_core.mcp.client")


@dataclass
class MCPTransportConfig:
    """
    Transport config drawn from capability.execution.transport.
    kind: "http" (supports SSE or streamable HTTP depending on protocol_path presence/value)
    """
    kind: str  # "http" (SSE or streamable_http) | "stdio" (future)
    base_url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    protocol_path: Optional[str] = "/mcp"
    verify_tls: Optional[bool] = None
    timeout_sec: Optional[int] = 30


def _safe_preview(obj: Any, limit: int = 800) -> str:
    try:
        if isinstance(obj, str):
            s = obj
        else:
            s = json.dumps(obj, ensure_ascii=False, default=str)
        return s if len(s) <= limit else s[:limit] + "…"
    except Exception:
        return "<unserializable>"


class MCPConnection:
    """
    Thin async wrapper using langchain-mcp-adapters.
    - Supports SSE and streamable HTTP (if protocol_path suggests /mcp or is None).
    - Discovers LangChain tools and invokes them by name.
    """

    def __init__(self) -> None:
        self._client: Optional[MultiServerMCPClient] = None
        self._tools: Dict[str, BaseTool] = {}
        # Stored for list_tools_raw() — raw MCP session needs the resolved URL + headers
        self._server_url: str = ""
        self._server_headers: Dict[str, str] = {}
        self._use_transport: str = "streamable_http"

    @classmethod
    async def connect(cls, cfg: MCPTransportConfig) -> "MCPConnection":
        if cfg.kind != "http":
            raise ValueError(f"Unsupported MCP transport kind: {cfg.kind}")
        if not cfg.base_url:
            raise ValueError("MCP HTTP transport requires base_url")

        base = cfg.base_url.rstrip("/")

        # Heuristic:
        # - If protocol_path is a typical protocol path (e.g., "/mcp"), use SSE.
        # - If protocol_path is "/mcp" (common REST/streamable route) or missing/empty, use streamable_http at /mcp.
        protocol_path = (cfg.protocol_path or "").strip() or "/mcp"
        looks_like_streamable = protocol_path.lower() in {"/mcp", "mcp"}
        use_transport = "streamable_http" if looks_like_streamable else "sse"
        url = f"{base}/mcp" if use_transport == "streamable_http" else f"{base}{protocol_path}"

        # Redact any sensitive header values
        redacted_headers = {}
        for k, v in (cfg.headers or {}).items():
            if k.lower() in {"authorization", "x-api-key", "api-key"}:
                redacted_headers[k] = "***"
            else:
                redacted_headers[k] = v

        logger.info(
            "[MCP] Connecting: transport=%s url=%s timeout=%ss verify_tls=%s headers=%s",
            use_transport, url, cfg.timeout_sec, cfg.verify_tls, _safe_preview(redacted_headers, 200)
        )

        conn = cls()
        conn._client = MultiServerMCPClient(
            {
                "server": {
                    "transport": use_transport,  # "sse" or "streamable_http"
                    "url": url,
                    "headers": cfg.headers or {},
                }
            }
        )
        conn._server_url = url
        conn._server_headers = cfg.headers or {}
        conn._use_transport = use_transport
        return conn

    async def aclose(self) -> None:
        try:
            if self._client and hasattr(self._client, "aclose"):
                await cast(Any, self._client).aclose()
                logger.info("[MCP] Connection closed")
        except Exception:
            logger.warning("[MCP] Error while closing connection", exc_info=True)

    async def list_tools(self) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Returns [(tool_name, json_schema_dict), ...] and caches tool objects for later invocation.
        """
        assert self._client is not None, "MCP client not connected"
        logger.info("[MCP] Discovering tools…")
        tools = await self._client.get_tools()
        self._tools = {t.name: t for t in tools}

        names = [t.name for t in tools]
        logger.info("[MCP] Discovered %d tool(s): %s", len(names), ", ".join(names) or "<none>")

        out: List[Tuple[str, Dict[str, Any]]] = []
        for t in tools:
            schema: Dict[str, Any] = {}
            try:
                raw = getattr(t, "args_schema", None)
                if isinstance(raw, dict):
                    # langchain-mcp-adapters 0.2+ passes inputSchema dict directly
                    schema = raw
                elif raw is not None:
                    if hasattr(raw, "model_json_schema"):
                        schema = raw.model_json_schema()  # Pydantic v2 class
                    elif hasattr(raw, "schema"):
                        schema = raw.schema()  # Pydantic v1 class
                if not schema and hasattr(t, "args") and isinstance(t.args, dict):
                    schema = t.args
            except Exception:
                schema = {}
            out.append((t.name, schema or {}))

        # Small preview of first few schemas for debugging
        preview = [{ "name": n, "args_schema_keys": list((s or {}).get("properties", {}).keys())[:6] } for n, s in out[:5]]
        logger.info("[MCP] Tool schema preview (first 5): %s", _safe_preview(preview, 600))

        return out

    async def list_tools_raw(self) -> List[Tuple[str, Dict[str, Any], Optional[Dict[str, Any]]]]:
        """
        Returns (tool_name, input_schema, output_schema) triples via a raw MCP session.
        output_schema is None if the server does not declare one for that tool.
        Unlike list_tools(), this method uses the raw MCP SDK (not langchain-mcp-adapters)
        so it captures outputSchema from the tools/list response.
        Intended for use by the onboarding service — not used in the execution path.
        """
        out: List[Tuple[str, Dict[str, Any], Optional[Dict[str, Any]]]] = []
        try:
            if self._use_transport == "streamable_http":
                from mcp.client.streamable_http import streamablehttp_client
                cm = streamablehttp_client(self._server_url, headers=self._server_headers)
            else:
                from mcp.client.sse import sse_client
                cm = sse_client(self._server_url, headers=self._server_headers)

            from mcp import ClientSession
            async with cm as transport:
                read, write = transport[0], transport[1]
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    for tool in result.tools:
                        in_schema: Dict[str, Any] = {}
                        raw_in = tool.inputSchema
                        if isinstance(raw_in, dict):
                            in_schema = raw_in
                        elif hasattr(raw_in, "model_dump"):
                            in_schema = raw_in.model_dump()

                        out_schema: Optional[Dict[str, Any]] = None
                        raw_out = getattr(tool, "outputSchema", None)
                        if raw_out:
                            if isinstance(raw_out, dict):
                                out_schema = raw_out
                            elif hasattr(raw_out, "model_dump"):
                                out_schema = raw_out.model_dump()

                        out.append((tool.name, in_schema, out_schema))
        except Exception:
            logger.warning("[MCP] list_tools_raw() failed; returning empty list", exc_info=True)
        return out

    async def invoke_tool(self, name: str, args: Dict[str, Any]) -> Any:
        """
        Invokes the tool by name with args (dict). Returns the raw tool result.
        """
        tool = self._tools.get(name)
        if not tool:
            # Refresh once if cache stale
            await self.list_tools()
            tool = self._tools.get(name)
        if not tool:
            raise ValueError(f"MCP tool '{name}' not found")

        logger.info("[MCP] Invoking tool: %s args=%s", name, _safe_preview(args, 600))
        result = await tool.ainvoke(args)
        logger.debug("[MCP] Tool result sample: %s", _safe_preview(result, 800))
        return result
