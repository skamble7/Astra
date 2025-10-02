# services/conductor-service/app/mcp_host/transports/stdio_client.py
from __future__ import annotations

import asyncio
import logging
import os
import re
from contextlib import AsyncExitStack, suppress
from typing import Any, AsyncIterator, Dict, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.mcp_host.types import DiscoveryReport, InvokePage, InvokeResult

logger = logging.getLogger("app.mcp.stdio")


class StdioMcpClient:
    """
    STDIO transport using the official MCP SDK.

    Improvements over the base version:
      - Unbuffered server I/O by default (PYTHONUNBUFFERED=1) to avoid hangs
      - Timeouts on initialize() and list_tools() so we fail fast
      - Clean shutdown to avoid anyio cancel-scope warnings
      - cwd/env are forwarded to the child process
    """

    def __init__(
        self,
        *,
        command: str,
        args: list[str] | None = None,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        readiness_regex: str = r".*",
        restart_on_exit: bool = True,   # reserved for future supervision
        kill_timeout_sec: int = 10,     # reserved for future supervision
        timeout_sec: int = 60,
    ) -> None:
        self.command = command
        self.args = args or []
        self.cwd = cwd

        # Ensure unbuffered Python in the server by default; allow caller overrides
        default_env = {"PYTHONUNBUFFERED": "1"}
        self.env = {**default_env, **(env or {})}

        self.readiness_regex = re.compile(readiness_regex, re.IGNORECASE)
        self.restart_on_exit = restart_on_exit
        self.kill_timeout_sec = kill_timeout_sec
        self.timeout_sec = timeout_sec

        self._connected = False
        self._session: ClientSession | None = None
        self._exit_stack: AsyncExitStack | None = None  # owns the stdio_client CM

    async def connect(self) -> "StdioMcpClient":
        if self._connected:
            return self

        params = StdioServerParameters(
            command=self.command,
            args=self.args,
            env={**os.environ, **self.env} if self.env else None,
            cwd=self.cwd,
        )

        self._exit_stack = AsyncExitStack()
        try:
            # Acquire the stdio client (spawns the child process and wires pipes)
            client_cm = stdio_client(params)
            read_stream, write_stream = await self._exit_stack.enter_async_context(client_cm)

            # Create a high-level session over the pipes
            self._session = ClientSession(read_stream, write_stream)

            # Initialization must complete in time
            await asyncio.wait_for(self._session.initialize(), timeout=self.timeout_sec)

            # Lightweight readiness check (also time-bounded)
            _tools = await asyncio.wait_for(self._session.list_tools(), timeout=self.timeout_sec)
            logger.debug("MCP tools discovered: %s", [t.name for t in getattr(_tools, "tools", [])])

            self._connected = True
            logger.info("MCP STDIO connected: %s %s (cwd=%s)", self.command, " ".join(self.args), self.cwd or ".")
            return self

        except Exception:
            # If anything failed during connect, unwind what we acquired so far
            with suppress(Exception):
                if self._session is not None:
                    await self._session.close()
            with suppress(Exception):
                if self._exit_stack is not None:
                    await self._exit_stack.aclose()
            self._session = None
            self._exit_stack = None
            raise

    async def close(self) -> None:
        if not self._connected and self._exit_stack is None and self._session is None:
            return

        try:
            if self._session is not None:
                with suppress(Exception):
                    await self._session.close()
        finally:
            self._session = None

        # Close the underlying stdio client context last
        if self._exit_stack is not None:
            with suppress(Exception):
                await self._exit_stack.aclose()
            self._exit_stack = None

        self._connected = False
        logger.info("MCP STDIO closed")

    async def discovery(self) -> DiscoveryReport:
        if not self._connected:
            await self.connect()
        assert self._session is not None

        tools_resp = await asyncio.wait_for(self._session.list_tools(), timeout=self.timeout_sec)
        resources_resp = await asyncio.wait_for(self._session.list_resources(), timeout=self.timeout_sec)
        prompts_resp = await asyncio.wait_for(self._session.list_prompts(), timeout=self.timeout_sec)

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
            # result.content is a list[ContentBlock]; convert to dicts
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