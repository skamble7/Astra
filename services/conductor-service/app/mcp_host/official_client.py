# services/conductor-service/app/mcp_host/official_client.py
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shutil
from typing import Any, Dict, Iterable, Optional

from mcp.client.session import ClientSession

# stdio
try:
    from mcp.client.stdio import stdio_client, StdioServerParameters  # type: ignore
    HAVE_SERVER_PARAMS = True
except Exception:
    from mcp.client.stdio import stdio_client  # type: ignore
    StdioServerParameters = None  # type: ignore
    HAVE_SERVER_PARAMS = False

# SSE (HTTP)
from mcp.client.sse import sse_client  # type: ignore

logger = logging.getLogger("app.mcp.official")


def _safe_env_for_log(env: Dict[str, str]) -> Dict[str, str]:
    shown: Dict[str, str] = {}
    if "PATH" in env:
        shown["PATH"] = env["PATH"]
    for k, v in env.items():
        if k.startswith("MCP_"):
            shown[k] = v
    return shown


# ──────────────────────────────────────────────────────────────────────────────
# STDIO CLIENT
# ──────────────────────────────────────────────────────────────────────────────

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

        self._ctx = None
        self._read = None
        self._write = None
        self._session: Optional[ClientSession] = None

    async def _preflight_check(self) -> None:
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
                logger.info("MCP preflight ok. help: %s",
                            (outs or b"")[:120].decode(errors="ignore"))
        except FileNotFoundError:
            logger.error("MCP binary not found on PATH: %s", self.command)
            raise
        except Exception:
            logger.warning("MCP preflight raised; continuing.", exc_info=True)

    async def connect(self) -> None:
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

        if self.preflight:
            await self._preflight_check()

        if HAVE_SERVER_PARAMS and StdioServerParameters is not None:
            server = StdioServerParameters(
                command=self.command,
                args=self.args,
                env=self.env or None,
                cwd=self.cwd or None,
            )
            self._ctx = stdio_client(server)
        else:
            try:
                self._ctx = stdio_client(  # type: ignore[arg-type]
                    self.command, self.args, env=self.env or None, cwd=self.cwd or None
                )
            except TypeError:
                self._ctx = stdio_client(  # type: ignore[arg-type]
                    [self.command, *self.args], env=self.env or None, cwd=self.cwd or None
                )

        self._read, self._write = await self._ctx.__aenter__()  # type: ignore[union-attr]
        self._session = ClientSession(self._read, self._write)
        try:
            await asyncio.wait_for(self._session.initialize(), timeout=self.init_timeout_sec)
        except asyncio.TimeoutError:
            # one quick retry — helpful if the process is still warming up
            logger.warning(
                "MCP stdio initialize() timed out after %ss; retrying once...",
                self.init_timeout_sec,
            )
            await asyncio.wait_for(self._session.initialize(), timeout=self.init_timeout_sec)
        logger.info("MCP stdio session initialized.")

    async def discovery(self) -> Dict[str, Any]:
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
        if not self._session:
            raise RuntimeError("MCP client not connected")

        logger.info("MCP stdio call: tool=%s args=%s", tool_name, _preview(args))
        async def _call():
            return await self._session.call_tool(tool_name, arguments=args)

        result = await asyncio.wait_for(_call(), timeout=timeout_sec)
        return _format_result(result)

    async def close(self) -> None:
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


# ──────────────────────────────────────────────────────────────────────────────
# HTTP SSE CLIENT
# ──────────────────────────────────────────────────────────────────────────────

class McpHttpSseClient:
    def __init__(
        self,
        *,
        base_url: str,
        sse_path: str = "/sse",
        headers: Optional[Dict[str, str]] = None,
        init_timeout_sec: int = 300,    # generous for initialize only
        health_path: Optional[str] = "/health",
        verify_tls: bool = True,        # not exposed in sdk today
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.sse_url = self.base_url + (sse_path if sse_path.startswith("/") else "/" + sse_path)
        self.headers = {"Accept": "text/event-stream", **(headers or {})}
        self.init_timeout_sec = int(init_timeout_sec)
        self.health_path = health_path
        self.verify_tls = verify_tls

        self._ctx = None
        self._read = None
        self._write = None
        self._session: Optional[ClientSession] = None

    async def connect(self) -> None:
        logger.info("Connecting MCP SSE: url=%s", self.sse_url)

        # IMPORTANT: official SDK expects positional SSE URL (no base_url= kwarg)
        self._ctx = sse_client(self.sse_url, headers=self.headers)  # type: ignore[arg-type]
        self._read, self._write = await self._ctx.__aenter__()      # type: ignore[union-attr]

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

    async def discovery(self) -> Dict[str, Any]:
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
        if not self._session:
            raise RuntimeError("MCP client not connected")

        logger.info("MCP sse call: tool=%s args=%s", tool_name, _preview(args))
        async def _call():
            return await self._session.call_tool(tool_name, arguments=args)

        result = await asyncio.wait_for(_call(), timeout=timeout_sec)
        return _format_result(result)

    async def close(self) -> None:
        try:
            if self._session:
                await self._session.shutdown()
        except Exception:
            logger.debug("Ignoring MCP session shutdown error (sse)", exc_info=True)

        if self._ctx:
            try:
                await self._ctx.__aexit__(None, None, None)  # type: ignore[union-attr]
            except Exception:
                logger.debug("Ignoring MCP sse context exit error", exc_info=True)

        self._ctx = None
        self._session = None
        self._read = None
        self._write = None


# ──────────────────────────────────────────────────────────────────────────────
# CAPABILITY-DRIVEN BUILDER (SSE or STDIO)
# ──────────────────────────────────────────────────────────────────────────────

def _format_result(result: Any) -> Dict[str, Any]:
    """Unify into {pages: [{data:{content,structured},cursor:None}], stream:None, metrics:{}}."""
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
    try:
        s = json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        s = str(obj)
    return s if len(s) <= limit else s[:limit] + f"...(+{len(s)-limit}B)"

async def build_client_from_capability(capability: Dict[str, Any]):
    """
    Build & connect an MCP client from a capability document (supports http+sse and stdio).
    """
    execution = (capability or {}).get("execution") or {}
    if execution.get("mode") != "mcp":
        raise ValueError("Capability must be 'mode: mcp'")

    transport = (execution.get("transport") or {})
    kind = (transport.get("kind") or "").lower()

    # NOTE: We now decouple init timeouts from tool timeouts.
    #       - init_timeout_sec: used only for session.initialize()
    #       - per tool: timeout set from tool_calls[i].timeout_sec (fallback to 120)
    init_timeout_sec = int(transport.get("init_timeout_sec", 300))

    if kind == "http":
        client = McpHttpSseClient(
            base_url=(transport.get("base_url") or "").rstrip("/"),
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
    "McpHttpSseClient",
    "build_client_from_capability",
]