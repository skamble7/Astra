# services/conductor-service/app/mcp_host/transports/stdio_client.py
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, AsyncIterator, Dict, Optional

from mcp import ClientSession, StdioServerParameters          # official SDK
from mcp.client.stdio import stdio_client                     # official STDIO transport

from app.mcp_host.types import DiscoveryReport, InvokePage, InvokeResult

logger = logging.getLogger("app.mcp.stdio")


class StdioMcpClient:
    """
    STDIO transport using the official SDK client. We supervise readiness via a regex,
    but rely primarily on session.initialize() succeeding as a hard signal the server is up.
    """

    def __init__(
        self,
        *,
        command: str,
        args: list[str] | None = None,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        readiness_regex: str = r"server started",
        restart_on_exit: bool = True,       # reserved for future supervisor
        kill_timeout_sec: int = 10,         # reserved for future supervisor
        timeout_sec: int = 60,
    ) -> None:
        self.command = command
        self.args = args or []
        self.cwd = cwd
        self.env = env or {}
        self.readiness_regex = re.compile(readiness_regex, re.IGNORECASE)
        self.restart_on_exit = restart_on_exit
        self.kill_timeout_sec = kill_timeout_sec
        self.timeout_sec = timeout_sec

        self._connected = False
        self._session: ClientSession | None = None
        self._client_cm = None  # ctx manager for stdio_client

    async def connect(self) -> "StdioMcpClient":
        if self._connected:
            return self

        params = StdioServerParameters(
            command=self.command,
            args=self.args,
            env={**os.environ, **self.env} if self.env else None,
            cwd=self.cwd,
        )

        # Open the stdio pipes and then the high-level session
        self._client_cm = stdio_client(params)
        read_stream, write_stream = await self._client_cm.__aenter__()

        self._session = ClientSession(read_stream, write_stream)
        await self._session.initialize()

        # Light readiness check (tools listing)
        await self._session.list_tools()
        self._connected = True
        logger.info("MCP STDIO connected: %s %s", self.command, " ".join(self.args))
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
            if self._client_cm is not None:
                await self._client_cm.__aexit__(None, None, None)
        except Exception:
            logger.debug("Ignoring STDIO client close error", exc_info=True)
        finally:
            self._connected = False
            self._session = None
            self._client_cm = None
            logger.info("MCP STDIO closed")

    async def discovery(self) -> DiscoveryReport:
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
        del cursor  # not supported in high-level call_tool
        assert self._session is not None

        result = await asyncio.wait_for(
            self._session.call_tool(tool, arguments=args),
            timeout=timeout_sec,
        )

        data: Dict[str, Any] = {}
        structured = getattr(result, "structuredContent", None)
        if structured is not None:
            data["structured"] = structured
        content = getattr(result, "content", None)
        if content is not None:
            data["content"] = [cb.model_dump() for cb in content]  # type: ignore[attr-defined]

        return [InvokePage(data=data, cursor=None)]

    async def _invoke_streaming(
        self, *, tool: str, args: Dict[str, Any], cursor: Optional[str], timeout_sec: int
    ) -> AsyncIterator[InvokePage]:
        del tool, args, cursor, timeout_sec
        async def _err() -> AsyncIterator[InvokePage]:
            raise NotImplementedError(
                "Streaming tool calls are not supported via the MCP Python SDK high-level client. "
                "Use non-streaming mode or implement a server-specific streaming protocol."
            )
            yield
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

        if cancel and cancel.is_cancelled:
            raise asyncio.CancelledError()

        if expects_stream:
            stream = await self._invoke_streaming(tool=tool, args=args, cursor=cursor, timeout_sec=timeout_sec)
            return InvokeResult(stream=stream, metrics={})
        else:
            pages = await self._invoke_non_streaming(tool=tool, args=args, cursor=cursor, timeout_sec=timeout_sec)
            return InvokeResult(pages=pages, metrics={})