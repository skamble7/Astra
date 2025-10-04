# app/agent/mcp/mcp_client.py
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, cast

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger("app.agent.mcp.client")


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
                if hasattr(t, "args_schema") and t.args_schema is not None:
                    schema = (
                        t.args_schema.schema()
                        if hasattr(t.args_schema, "schema")
                        else t.args_schema.model_json_schema()  # type: ignore[attr-defined]
                    )
                elif hasattr(t, "args") and isinstance(t.args, dict):
                    schema = t.args
            except Exception:
                schema = {}
            out.append((t.name, schema or {}))

        # Small preview of first few schemas for debugging
        preview = [{ "name": n, "args_schema_keys": list((s or {}).get("properties", {}).keys())[:6] } for n, s in out[:5]]
        logger.debug("[MCP] Tool schema preview (first 5): %s", _safe_preview(preview, 600))

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