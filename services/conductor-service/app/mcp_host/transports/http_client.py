from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator, Dict, Optional

from mcp import ClientSession  # official SDK session
from mcp.client.streamable_http import streamablehttp_client  # official HTTP transport

from app.mcp_host.types import DiscoveryReport, InvokePage, InvokeResult

logger = logging.getLogger("app.mcp.http")


class HttpMcpClient:
    """
    Streamable HTTP transport for MCP.

    Notes:
      * SSE is deprecated in the SDK/spec; we use Streamable HTTP as the default network transport.
      * The SDK's call_tool is request/response (non-streaming). If a server implements bespoke
        streaming for tools, we can extend this, but for now expects_stream is not supported here.
    """

    def __init__(
        self,
        *,
        base_url: str,
        headers: Optional[Dict[str, str]] = None,
        verify_tls: bool = True,   # kept for parity; the SDK uses underlying httpx settings
        timeout_sec: int = 60,
        sse_path: str = "/sse",    # kept for parity with our capability schema (unused)
        health_path: str = "/health",  # not required; we rely on initialize() + a cheap call
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}
        self.verify_tls = verify_tls
        self.timeout_sec = timeout_sec

        self._connected = False
        self._read = None
        self._write = None
        self._session: ClientSession | None = None

    async def connect(self) -> "HttpMcpClient":
        """
        Open the Streamable HTTP connection and initialize the session.
        """
        if self._connected:
            return self

        # The client yields a (read, write, session_id) triple.
        # We'll persist read/write for the lifetime of this client.
        self._read = None
        self._write = None

        # The context manager must remain open for the session lifetime.
        # We keep it by storing the task and ensuring close() cancels it.
        self._connector_cm = streamablehttp_client(  # type: ignore[attr-defined]
            self.base_url,
            headers=self.headers or None,
            timeout=self.timeout_sec,
        )
        self._connector = await self._connector_cm.__aenter__()  # (read, write, session_id)
        read_stream, write_stream, _session_id = self._connector

        self._session = ClientSession(read_stream, write_stream)
        await self._session.initialize()

        # A cheap discovery call to assert readiness.
        await self._session.list_tools()
        self._connected = True
        logger.info("MCP Streamable HTTP connected: %s", self.base_url)
        return self

    async def close(self) -> None:
        if not self._connected:
            return
        try:
            if self._session:
                await self._session.close()
        except Exception:
            logger.debug("Ignoring MCP session close error", exc_info=True)
        try:
            # Close the transport connector context manager
            if getattr(self, "_connector_cm", None) is not None:
                await self._connector_cm.__aexit__(None, None, None)
        except Exception:
            logger.debug("Ignoring HTTP connector close error", exc_info=True)
        finally:
            self._connected = False
            self._session = None
            self._connector_cm = None
            self._connector = None
            logger.info("MCP Streamable HTTP closed: %s", self.base_url)

    async def discovery(self) -> DiscoveryReport:
        """
        List tools/resources/prompts via the SDK.
        """
        if not self._connected:
            await self.connect()
        assert self._session is not None

        tools_resp = await self._session.list_tools()
        resources_resp = await self._session.list_resources()
        prompts_resp = await self._session.list_prompts()

        tools = [t.name for t in getattr(tools_resp, "tools", [])]
        resources = [r.model_dump() for r in getattr(resources_resp, "resources", [])]
        prompts = [p.model_dump() for p in getattr(prompts_resp, "prompts", [])]

        return DiscoveryReport(tools=tools, resources=resources, prompts=prompts)

    async def _invoke_non_streaming(
        self, *, tool: str, args: Dict[str, Any], cursor: Optional[str], timeout_sec: int
    ) -> list[InvokePage]:
        """
        The SDK's call_tool is a simple request/response. We wrap it into our page shape.
        """
        del cursor  # not supported by call_tool in SDK; servers can implement paging in content
        assert self._session is not None
        result = await asyncio.wait_for(
            self._session.call_tool(tool, arguments=args),
            timeout=timeout_sec,
        )

        # Normalize the result to a dict for our pipeline. The SDK returns a model with:
        #   - content: list[TextContent | ImageContent | ...]
        #   - structuredContent: Any | None
        # We'll prefer structuredContent if present; else a best-effort dict of content.
        data: Dict[str, Any] = {}
        structured = getattr(result, "structuredContent", None)
        if structured is not None:
            data["structured"] = structured
        content = getattr(result, "content", None)
        if content is not None:
            # convert content blocks to plain JSON (pydantic models -> dict)
            data["content"] = [cb.model_dump() for cb in content]  # type: ignore[attr-defined]

        return [InvokePage(data=data, cursor=None)]

    async def _invoke_streaming(
        self, *, tool: str, args: Dict[str, Any], cursor: Optional[str], timeout_sec: int
    ) -> AsyncIterator[InvokePage]:
        """
        The high-level SDK does not expose a streaming variant for call_tool.
        We surface a clear error so callers can adjust (e.g., use non-streaming).
        """
        del tool, args, cursor, timeout_sec
        async def _err() -> AsyncIterator[InvokePage]:
            raise NotImplementedError(
                "Streaming tool calls are not supported via the MCP Python SDK high-level client. "
                "Use non-streaming mode or implement a server-specific streaming protocol."
            )
            yield  # make this an async generator
        return _err()

    async def invoke_tool(
        self,
        *,
        tool: str,
        args: Dict[str, Any],
        expects_stream: bool,
        cursor: Optional[str],
        cancel: "CancelToken | None",
        timeout_sec: int,
    ) -> InvokeResult:
        if not self._connected:
            await self.connect()

        # Cooperative cancel (pre-dispatch)
        if cancel and cancel.is_cancelled:
            raise asyncio.CancelledError()

        if expects_stream:
            stream = await self._invoke_streaming(tool=tool, args=args, cursor=cursor, timeout_sec=timeout_sec)
            return InvokeResult(stream=stream, metrics={})
        else:
            pages = await self._invoke_non_streaming(tool=tool, args=args, cursor=cursor, timeout_sec=timeout_sec)
            return InvokeResult(pages=pages, metrics={})