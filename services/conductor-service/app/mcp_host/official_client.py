# app/mcp_host/official_client.py
from __future__ import annotations
import asyncio, logging, os, shutil, contextlib
from typing import Any, Dict, Iterable, Optional
from mcp.client.session import ClientSession

try:
    from mcp.client.stdio import stdio_client, StdioServerParameters
    HAVE_SERVER_PARAMS = True
except Exception:
    from mcp.client.stdio import stdio_client  # type: ignore
    StdioServerParameters = None  # type: ignore
    HAVE_SERVER_PARAMS = False

logger = logging.getLogger("app.mcp.official")

def _safe_env_for_log(env: Dict[str, str]) -> Dict[str, str]:
    shown: Dict[str, str] = {}
    if "PATH" in env: shown["PATH"] = env["PATH"]
    for k, v in env.items():
        if k.startswith("MCP_"):
            shown[k] = v
    return shown

class McpStdIoClient:
    def __init__(
        self,
        *,
        command: str,
        args: Iterable[str] | None = None,
        env: Dict[str, str] | None = None,
        cwd: Optional[str] = None,
        timeout_sec: int = 600,           # generous startup window
        preflight: bool = True,           # quick sanity check
    ) -> None:
        self.command = command
        self.args = list(args or [])
        self.env = dict(env or {})
        self.cwd = cwd
        self.timeout_sec = int(timeout_sec)
        self.preflight = bool(preflight)

        self._ctx = None
        self._read = None
        self._write = None
        self._session: Optional[ClientSession] = None

    async def _preflight_check(self) -> None:
        """Try `<cmd> --help` to confirm it executes & is on PATH."""
        try:
            proc = await asyncio.create_subprocess_exec(
                self.command, "--help",
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
                logger.warning("MCP preflight timed out (help). Proceeding anyway.")
                return
            if proc.returncode != 0:
                logger.warning(
                    "MCP preflight returned non-zero (%s). stderr=%s",
                    proc.returncode, (errs or b"").decode(errors="ignore")[:500],
                )
            else:
                logger.info("MCP preflight ok. First help bytes: %s",
                            (outs or b"")[:120].decode(errors="ignore"))
        except FileNotFoundError:
            logger.error("MCP binary not found on PATH: %s", self.command)
            raise
        except Exception:
            logger.warning("MCP preflight raised; continuing.", exc_info=True)

    async def connect(self) -> None:
        # Ensure PATH includes container PATH
        self.env.setdefault("PATH", os.environ.get("PATH", ""))

        exe_path = shutil.which(self.command, path=self.env.get("PATH"))
        argv = [self.command, *self.args]
        logger.info(
            "Starting MCP stdio server: exe=%s argv=%s cwd=%s env=%s",
            exe_path or "(not found on PATH)", " ".join(argv),
            self.cwd or "(none)", _safe_env_for_log(self.env),
        )

        if self.preflight:
            await self._preflight_check()

        # Build stdio client per SDK variant
        if HAVE_SERVER_PARAMS and StdioServerParameters is not None:
            server = StdioServerParameters(
                command=self.command, args=self.args,
                env=self.env or None, cwd=self.cwd or None,
            )
            self._ctx = stdio_client(server)
        else:
            try:
                self._ctx = stdio_client(self.command, self.args, env=self.env or None, cwd=self.cwd or None)  # type: ignore[arg-type]
            except TypeError:
                self._ctx = stdio_client([self.command, *self.args], env=self.env or None, cwd=self.cwd or None)  # type: ignore[arg-type]

        # Enter async context -> pipes
        self._read, self._write = await self._ctx.__aenter__()  # type: ignore[union-attr]

        # Initialize MCP session (handshake)
        self._session = ClientSession(self._read, self._write)
        try:
            await asyncio.wait_for(self._session.initialize(), timeout=self.timeout_sec)
        except asyncio.TimeoutError:
            logger.error(
                "Timed out waiting for MCP initialize() after %ss. "
                "The server likely didn't start the MCP loop or crashed before handshake.",
                self.timeout_sec,
            )
            raise
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

    async def invoke_tool(
        self,
        *,
        tool: str,
        args: Dict[str, Any],
        timeout_sec: int = 180,
        expects_stream: bool = False,
        cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self._session:
            raise RuntimeError("MCP client not connected")

        async def _call():
            return await self._session.call_tool(tool, arguments=args)

        result = await asyncio.wait_for(_call(), timeout=timeout_sec)
        pages = [
            {
                "data": {
                    "content": result.content,
                    "structured": getattr(result, "data", None),
                },
                "cursor": None,
            }
        ]
        return {"pages": pages, "stream": None, "metrics": {}}

    async def close(self) -> None:
        try:
            if self._session:
                await self._session.shutdown()
        except Exception:
            logger.debug("Ignoring MCP session shutdown error", exc_info=True)

        if self._ctx:
            try:
                await self._ctx.__aexit__(None, None, None)  # type: ignore[union-attr]
            except Exception:
                logger.debug("Ignoring MCP stdio context exit error", exc_info=True)

        self._ctx = None
        self._session = None
        self._read = None
        self._write = None


def build_stdio_client_from_capability(capability: Dict[str, Any]) -> McpStdIoClient:
    """
    Build a McpStdIoClient from a capability document.

    Expected shape (minimum):
      {
        "execution": {
          "mode": "mcp",
          "transport": {
            "kind": "stdio",
            "command": "mcp-git-repo-snapshot",
            "args": ["serve"] or ["--stdio"],
            "env": {...},
            "cwd": "/workspace",
            "timeout_sec": 600
          }
        }
      }
    """
    execution = (capability or {}).get("execution") or {}
    if execution.get("mode") != "mcp":
        raise ValueError("Capability must be 'mode: mcp'")

    t = execution.get("transport") or {}
    if t.get("kind") != "stdio":
        raise ValueError("Only stdio transport supported by this builder")

    command = t.get("command") or "mcp-git-repo-snapshot"
    args = t.get("args") or []
    env = t.get("env") or {}
    cwd = t.get("cwd")
    timeout_sec = int(t.get("timeout_sec", 600))

    # Ensure PATH exists (so shutil.which works in container)
    env.setdefault("PATH", os.environ.get("PATH", ""))

    return McpStdIoClient(
        command=command,
        args=args,
        env=env,
        cwd=cwd,
        timeout_sec=timeout_sec,
        preflight=True,
    )

__all__ = [
    "McpStdIoClient",
    "build_stdio_client_from_capability",
]