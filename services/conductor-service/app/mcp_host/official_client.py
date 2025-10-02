"""
Official MCP client for the conductor service.

This module provides client classes for connecting to Model Context
Protocol (MCP) servers using the official Python SDK.  It supports
three transport modes:

* **stdio** – launch a local MCP server binary and communicate over
  standard input/output streams.
* **streamable HTTP** – use a single HTTP endpoint that accepts POST
  requests and optionally returns server‑sent events (SSE) for
  streaming responses.  This is the recommended transport for remote
  servers as of MCP version 2025‑03‑26.
* **HTTP+SSE** – legacy transport where the client opens an SSE stream
  and receives an "endpoint" event indicating where to send POST
  requests.  This mode is kept for backwards compatibility with
  servers predating the streamable HTTP transport.

The :class:`McpHttpClient` implements a fallback strategy compliant
with the MCP specification: it first attempts to connect using the
streamable HTTP transport and, if that fails due to a 4xx response or
initialisation timeout, falls back to the legacy SSE transport.  The
helper function :func:`build_client_from_capability` constructs the
appropriate client from a capability document and establishes a
connection.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shutil
from typing import Any, Dict, Iterable, Optional, Tuple

from mcp.client.session import ClientSession

try:
    # stdio client
    from mcp.client.stdio import stdio_client, StdioServerParameters  # type: ignore
    HAVE_SERVER_PARAMS = True
except Exception:
    from mcp.client.stdio import stdio_client  # type: ignore
    StdioServerParameters = None  # type: ignore
    HAVE_SERVER_PARAMS = False

# SSE (legacy HTTP transport)
from mcp.client.sse import sse_client  # type: ignore

try:
    # Streamable HTTP (current HTTP transport)
    from mcp.client.streamable_http import streamablehttp_client  # type: ignore
    HAVE_STREAMABLE_HTTP = True
except Exception:
    streamablehttp_client = None  # type: ignore
    HAVE_STREAMABLE_HTTP = False

logger = logging.getLogger("app.mcp.official")


def _safe_env_for_log(env: Dict[str, str]) -> Dict[str, str]:
    """Return a redacted copy of environment variables for logging."""
    shown: Dict[str, str] = {}
    if "PATH" in env:
        shown["PATH"] = env["PATH"]
    for k, v in env.items():
        if k.startswith("MCP_"):
            shown[k] = v
    return shown


#
# ────────────────────────────────────────────────────────────────────────────
# STDIO CLIENT
#
# This client launches an MCP server binary locally and communicates over
# its standard input/output.  It supports a preflight check to invoke
# ``--help`` for logging and error reporting.
class McpStdIoClient:
    def __init__(
        self,
        *,
        command: str,
        args: Iterable[str] | None = None,
        env: Dict[str, str] | None = None,
        cwd: Optional[str] = None,
        init_timeout_sec: int = 300,
        preflight: bool = True,
    ) -> None:
        self.command = command
        self.args = list(args or [])
        self.env = dict(env or {})
        self.cwd = cwd
        self.init_timeout_sec = int(init_timeout_sec)
        self.preflight = bool(preflight)

        self._ctx: Optional[Any] = None
        self._read: Optional[Any] = None
        self._write: Optional[Any] = None
        self._session: Optional[ClientSession] = None

    async def _preflight_check(self) -> None:
        """Execute ``<command> --help`` to ensure the binary is present."""
        try:
            proc = await asyncio.create_subprocess_exec(
                self.command,
                "--help",
                cwd=self.cwd or None,
                env={**os.environ, **self.env} if self.env else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                outs, errs = await asyncio.wait_for(proc.communicate(), timeout=5)
            except asyncio.TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
                logger.warning("MCP preflight timed out (help). Proceeding.")
                return
            if proc.returncode != 0:
                logger.warning(
                    "MCP preflight non-zero (%s). stderr=%s",
                    proc.returncode,
                    (errs or b"").decode(errors="ignore")[:500],
                )
            else:
                logger.info(
                    "MCP preflight ok. help: %s",
                    (outs or b"")[:120].decode(errors="ignore"),
                )
        except FileNotFoundError:
            logger.error("MCP binary not found on PATH: %s", self.command)
            raise
        except Exception:
            logger.warning("MCP preflight raised; continuing.", exc_info=True)

    async def connect(self) -> None:
        """Launch the MCP server and initialise the session."""
        # Ensure PATH is present in environment
        self.env.setdefault("PATH", os.environ.get("PATH", ""))
        exe_path = shutil.which(self.command, path=self.env.get("PATH"))
        argv = [self.command, *self.args]
        logger.info(
            "Starting MCP stdio server: exe=%s argv=%s cwd=%s env=%s",
            exe_path or "(not found on PATH)",
            " ".join(argv),
            self.cwd or "(none)",
            _safe_env_for_log(self.env),
        )
        # Optional preflight to check the binary exists and is callable
        if self.preflight:
            await self._preflight_check()
        # Use newer constructor if available
        if HAVE_SERVER_PARAMS and StdioServerParameters is not None:
            server = StdioServerParameters(
                command=self.command,
                args=self.args,
                env=self.env or None,
                cwd=self.cwd or None,
            )
            self._ctx = stdio_client(server)
        else:
            # SDK versions prior to 0.8 use positional arguments
            try:
                self._ctx = stdio_client(
                    self.command, self.args, env=self.env or None, cwd=self.cwd or None
                )  # type: ignore[arg-type]
            except TypeError:
                # In some SDK versions the first argument can be a list
                self._ctx = stdio_client(
                    [self.command, *self.args], env=self.env or None, cwd=self.cwd or None
                )  # type: ignore[arg-type]
        # Enter the async context and create a session
        self._read, self._write = await self._ctx.__aenter__()  # type: ignore[union-attr]
        self._session = ClientSession(self._read, self._write)
        try:
            await asyncio.wait_for(self._session.initialize(), timeout=self.init_timeout_sec)
        except asyncio.TimeoutError:
            # A single retry helps when the process is still warming up
            logger.warning(
                "MCP stdio initialize() timed out after %ss; retrying once...",
                self.init_timeout_sec,
            )
            await asyncio.wait_for(self._session.initialize(), timeout=self.init_timeout_sec)
        logger.info("MCP stdio session initialized.")

    async def discovery(self) -> Dict[str, Any]:
        """Return available tools, resources and prompts from the server."""
        if not self._session:
            raise RuntimeError("MCP client not connected")
        tools = await self._session.list_tools()
        try:
            resources = await self._session.list_resources()
        except Exception:
            resources = []
        try:
            prompts = await self._session.list_prompts()
        except Exception:
            prompts = []
        return {
            "tools": [t.name for t in (tools or [])],
            "resources": resources or [],
            "prompts": prompts or [],
        }

    async def call_tool(self, tool_name: str, args: Dict[str, Any], timeout_sec: int) -> Dict[str, Any]:
        """Invoke an MCP tool with the provided arguments and timeout."""
        if not self._session:
            raise RuntimeError("MCP client not connected")
        logger.info("MCP stdio call: tool=%s args=%s", tool_name, _preview(args))

        async def _call():
            return await self._session.call_tool(tool_name, arguments=args)

        result = await asyncio.wait_for(_call(), timeout=timeout_sec)
        return _format_result(result)

    async def close(self) -> None:
        """Shutdown the MCP session and exit the context."""
        try:
            if self._session:
                await self._session.shutdown()
        except Exception:
            logger.debug("Ignoring MCP session shutdown error (stdio)", exc_info=True)
        if self._ctx:
            try:
                await self._ctx.__aexit__(None, None, None)  # type: ignore[union-attr]
            except Exception:
                logger.debug("Ignoring MCP stdio context exit error", exc_info=True)
        self._ctx = None
        self._session = None
        self._read = None
        self._write = None


#
# ────────────────────────────────────────────────────────────────────────────
# HTTP CLIENT (STREAMABLE + SSE FALLBACK)
#
# The MCP specification transitioned from a dual‑endpoint HTTP+SSE transport
# to a unified streamable HTTP endpoint.  This client follows the
# recommended connection sequence: it first attempts to connect to the
# MCP endpoint (streamable) and sends the initialisation request.  If
# the server responds with a 4xx error or the initialisation times out,
# it falls back to opening a legacy SSE stream and waiting for the
# initialisation there.
class McpHttpClient:
    def __init__(
        self,
        *,
        base_url: str,
        stream_path: str = "/mcp",
        sse_path: str = "/sse",
        headers: Optional[Dict[str, str]] = None,
        init_timeout_sec: int = 300,
        health_path: Optional[str] = "/health",
        verify_tls: bool = True,
    ) -> None:
        # Strip any trailing slash for consistent URL construction
        self.base_url = base_url.rstrip("/")
        # Full URLs for the streamable and SSE endpoints
        self.stream_url = self.base_url + (stream_path if stream_path.startswith("/") else "/" + stream_path)
        self.sse_url = self.base_url + (sse_path if sse_path.startswith("/") else "/" + sse_path)
        # Accept both JSON and SSE when posting to the streamable endpoint; for SSE only we accept text/event-stream
        default_headers = {"Accept": "application/json, text/event-stream"}
        self.headers = {**default_headers, **(headers or {})}
        self.init_timeout_sec = int(init_timeout_sec)
        self.health_path = health_path
        self.verify_tls = verify_tls
        # Internal state
        self._ctx: Optional[Any] = None
        self._read: Optional[Any] = None
        self._write: Optional[Any] = None
        self._session: Optional[ClientSession] = None
        # The following is used only for streamable HTTP; ignored for SSE
        self._get_session_id: Optional[Any] = None

    async def _connect_streamable(self) -> bool:
        """Attempt to connect using streamable HTTP; return True on success."""
        if not HAVE_STREAMABLE_HTTP or streamablehttp_client is None:
            return False
        try:
            logger.info("Connecting MCP HTTP (streamable): url=%s", self.stream_url)
            # Enter the streamable HTTP client context.  This returns a
            # (read_stream, write_stream, get_session_id) triple.
            self._ctx = streamablehttp_client(
                self.stream_url,
                headers=self.headers,
                verify_tls=self.verify_tls,
            )  # type: ignore[arg-type]
            self._read, self._write, self._get_session_id = await self._ctx.__aenter__()
            self._session = ClientSession(self._read, self._write)
            await asyncio.wait_for(self._session.initialize(), timeout=self.init_timeout_sec)
            logger.info("MCP streamable HTTP session initialized.")
            return True
        except asyncio.TimeoutError:
            logger.warning(
                "Timed out waiting for MCP initialize() after %ss (streamable http); falling back to legacy SSE...",
                self.init_timeout_sec,
            )
            # Clean up partially opened context before fallback
            await self._close_ctx()
            return False
        except Exception as exc:
            # A 4xx response (e.g., 404 or 405) manifests as an exception in the SDK
            logger.info("Streamable HTTP connection failed; falling back to legacy SSE: %s", exc)
            await self._close_ctx()
            return False

    async def _connect_sse(self) -> None:
        """Connect using the legacy HTTP+SSE transport."""
        logger.info("Connecting MCP SSE: url=%s", self.sse_url)
        # Accept header for SSE connection
        headers = {"Accept": "text/event-stream", **(self.headers or {})}
        self._ctx = sse_client(self.sse_url, headers=headers)  # type: ignore[arg-type]
        self._read, self._write = await self._ctx.__aenter__()  # type: ignore[union-attr]
        self._session = ClientSession(self._read, self._write)
        try:
            await asyncio.wait_for(self._session.initialize(), timeout=self.init_timeout_sec)
        except asyncio.TimeoutError:
            logger.warning(
                "Timed out waiting for MCP initialize() after %ss (sse); retrying once...",
                self.init_timeout_sec,
            )
            await asyncio.wait_for(self._session.initialize(), timeout=self.init_timeout_sec)
        logger.info("MCP SSE session initialized.")

    async def _close_ctx(self) -> None:
        """Exit any open context safely (internal use)."""
        if self._ctx is not None:
            try:
                await self._ctx.__aexit__(None, None, None)  # type: ignore[union-attr]
            except Exception:
                logger.debug("Ignoring MCP context exit error", exc_info=True)
        self._ctx = None
        self._session = None
        self._read = None
        self._write = None
        self._get_session_id = None

    async def connect(self) -> None:
        """Attempt to connect and initialise the session using streamable HTTP with SSE fallback."""
        # First try streamable HTTP; if unsuccessful, fall back to SSE
        success = await self._connect_streamable()
        if not success:
            await self._connect_sse()

    async def discovery(self) -> Dict[str, Any]:
        """Return available tools, resources and prompts from the server."""
        if not self._session:
            raise RuntimeError("MCP client not connected")
        tools = await self._session.list_tools()
        try:
            resources = await self._session.list_resources()
        except Exception:
            resources = []
        try:
            prompts = await self._session.list_prompts()
        except Exception:
            prompts = []
        return {
            "tools": [t.name for t in (tools or [])],
            "resources": resources or [],
            "prompts": prompts or [],
        }

    async def call_tool(self, tool_name: str, args: Dict[str, Any], timeout_sec: int) -> Dict[str, Any]:
        """Invoke an MCP tool with the provided arguments and timeout."""
        if not self._session:
            raise RuntimeError("MCP client not connected")
        logger.info("MCP http call: tool=%s args=%s", tool_name, _preview(args))

        async def _call():
            return await self._session.call_tool(tool_name, arguments=args)

        result = await asyncio.wait_for(_call(), timeout=timeout_sec)
        return _format_result(result)

    async def close(self) -> None:
        """Shutdown the MCP session and exit the context."""
        try:
            if self._session:
                await self._session.shutdown()
        except Exception:
            logger.debug("Ignoring MCP session shutdown error (http)", exc_info=True)
        await self._close_ctx()


#
# ────────────────────────────────────────────────────────────────────────────
# RESULT UTILITIES AND FACTORY
#
def _format_result(result: Any) -> Dict[str, Any]:
    """
    Unify result into the shape expected by the conductor service:

    ``{pages: [{data:{content,structured}, cursor: None}], stream: None, metrics: {}}``
    """
    pages = [
        {
            "data": {
                "content": getattr(result, "content", None),
                "structured": getattr(result, "data", None),
            },
            "cursor": None,
        }
    ]
    return {"pages": pages, "stream": None, "metrics": {}}


def _preview(obj: Any, limit: int = 1000) -> str:
    """Return a short, JSON serialisable preview of an object for logging."""
    try:
        s = json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        s = str(obj)
    return s if len(s) <= limit else s[:limit] + f"...(+{len(s)-limit}B)"


async def build_client_from_capability(capability: Dict[str, Any]):
    """
    Build and connect an MCP client from a capability document.

    The capability document describes how the agent should execute a tool.  The
    ``execution`` section must specify ``mode: mcp`` and a ``transport``
    configuration.  Supported transport kinds are ``"http"`` and ``"stdio"``.
    For ``"http"``, the client will attempt a streamable HTTP connection
    followed by an SSE fallback.  For ``"stdio"``, a local subprocess is
    launched.
    """
    execution = (capability or {}).get("execution") or {}
    if execution.get("mode") != "mcp":
        raise ValueError("Capability must be 'mode: mcp'")
    transport = execution.get("transport") or {}
    kind = (transport.get("kind") or "").lower()
    init_timeout_sec = int(transport.get("init_timeout_sec", 300))
    if kind == "http":
        client = McpHttpClient(
            base_url=(transport.get("base_url") or "").rstrip("/"),
            stream_path=transport.get("mcp_path") or "/mcp",
            sse_path=transport.get("sse_path") or "/sse",
            headers=transport.get("headers") or {},
            init_timeout_sec=init_timeout_sec,
            health_path=transport.get("health_path") or "/health",
            verify_tls=bool(transport.get("verify_tls", True)),
        )
        await client.connect()
        return client
    if kind == "stdio":
        command = transport.get("command") or "python"
        args = list(transport.get("args") or [])
        env = dict(transport.get("env") or {})
        cwd = transport.get("cwd")
        env.setdefault("PATH", os.environ.get("PATH", ""))
        client = McpStdIoClient(
            command=command,
            args=args,
            env=env,
            cwd=cwd,
            init_timeout_sec=init_timeout_sec,
            preflight=True,
        )
        await client.connect()
        return client
    raise ValueError(f"Unsupported MCP transport kind: {kind!r}")


__all__ = [
    "McpStdIoClient",
    "McpHttpClient",
    "build_client_from_capability",
]