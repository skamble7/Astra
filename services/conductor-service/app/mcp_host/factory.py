# services/conductor-service/app/mcp_host/factory.py
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any, Dict, Optional, Tuple

from app.mcp_host.client_manager import ClientManager
from app.mcp_host.discovery_validator import validate as validate_discovery
from app.mcp_host.types import ClientSignature, DiscoveryReport
from app.mcp_host.transports.http_client import HttpMcpClient
from app.mcp_host.transports.stdio_client import StdioMcpClient

logger = logging.getLogger("app.mcp.factory")

# A module-level manager dedicated to MCP transport clients.
mcp_client_manager: ClientManager[Any] = ClientManager[Any](capacity=32, idle_ttl_sec=900)


# --------- Signature helpers ------------------------------------------------ #

def _stable_hash(obj: Any) -> str:
    """
    Stable short hash for dict/list config values (headers/env/args).
    """
    try:
        blob = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except Exception:
        blob = str(obj)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


def transport_signature(execution: Dict[str, Any]) -> ClientSignature:
    """
    Build a stable signature string for the capability's MCP server transport.
    Used as the key for ClientManager reuse.

    - HTTP:  "http|<base_url>|<headersHash>"
    - STDIO: "stdio|<command>|<argsHash>|<envHash>|<cwdHash>"
    """
    mode = execution.get("mode")
    if mode != "mcp":
        raise ValueError("transport_signature requires an MCP execution (mode='mcp').")

    transport = execution.get("transport") or {}
    kind = transport.get("kind")
    if kind == "http":
        base_url = (transport.get("base_url") or "").rstrip("/")
        headers = transport.get("headers") or {}
        return f"http|{base_url}|{_stable_hash(headers)}"
    elif kind == "stdio":
        command = transport.get("command") or ""
        args = transport.get("args") or []
        env_aliases = transport.get("env_aliases") or {}
        env = transport.get("env") or {}
        cwd = transport.get("cwd") or ""
        return "stdio|" + "|".join(
            [
                command,
                _stable_hash(args),
                _stable_hash(env),
                _stable_hash(env_aliases),
                _stable_hash(cwd),
            ]
        )
    else:
        raise ValueError(f"Unsupported MCP transport kind: {kind!r}")


# --------- Client factory --------------------------------------------------- #

async def _create_http_client(transport: Dict[str, Any]) -> HttpMcpClient:
    client = HttpMcpClient(
        base_url=(transport.get("base_url") or "").rstrip("/"),
        headers=transport.get("headers") or {},
        verify_tls=bool(transport.get("verify_tls", True)),
        timeout_sec=int(transport.get("timeout_sec", 60)),
        sse_path=transport.get("sse_path") or "/sse",
        health_path=transport.get("health_path") or "/health",
    )
    await client.connect()
    return client


async def _create_stdio_client(transport: Dict[str, Any]) -> StdioMcpClient:
    command = transport.get("command") or ""
    args = transport.get("args") or []

    # 🔑 Always enforce unbuffered mode when running Python interpreters
    if command.strip().startswith("python") and "-u" not in args:
        args = ["-u"] + list(args)

    client = StdioMcpClient(
        command=command,
        args=args,
        cwd=transport.get("cwd"),
        env=transport.get("env") or {},
        readiness_regex=transport.get("readiness_regex") or r"server started",
        restart_on_exit=bool(transport.get("restart_on_exit", True)),
        kill_timeout_sec=int(transport.get("kill_timeout_sec", 10)),
        timeout_sec=int(transport.get("timeout_sec", 60)),
    )
    await client.connect()
    return client


async def build_client(execution: Dict[str, Any]) -> Any:
    """
    Build and connect a transport client based on a capability execution config (mode='mcp').
    Returns an initialized client instance (HttpMcpClient or StdioMcpClient).
    """
    if execution.get("mode") != "mcp":
        raise ValueError("build_client requires an MCP execution (mode='mcp').")

    transport = execution.get("transport") or {}
    kind = transport.get("kind")
    if kind == "http":
        return await _create_http_client(transport)
    elif kind == "stdio":
        return await _create_stdio_client(transport)
    else:
        raise ValueError(f"Unsupported MCP transport kind: {kind!r}")


# --------- Public entrypoints ---------------------------------------------- #

async def get_or_create_client(
    *,
    execution: Dict[str, Any],
    manager: ClientManager[Any] | None = None,
) -> Tuple[ClientSignature, Any]:
    """
    Get (or create & cache) a connected MCP client for the given capability execution.
    Returns (signature, client).
    """
    if execution.get("mode") != "mcp":
        raise ValueError("get_or_create_client requires an MCP execution (mode='mcp').")

    signature = transport_signature(execution)
    mgr = manager or mcp_client_manager

    async def _factory() -> Any:
        client = await build_client(execution)
        return client

    client = await mgr.get(signature, _factory)
    return signature, client


def required_tools_from_capability(capability: Dict[str, Any]) -> list[str]:
    """
    Extract tool names required by an MCP capability from its tool_calls spec.
    """
    exec_cfg = capability.get("execution") or {}
    if exec_cfg.get("mode") != "mcp":
        return []
    tool_calls = exec_cfg.get("tool_calls") or []
    tools = [tc.get("tool") for tc in tool_calls if isinstance(tc, dict) and tc.get("tool")]
    # de-dup preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for t in tools:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


async def ensure_discovery_and_validate(
    *,
    client: Any,
    capability_execution: Dict[str, Any],
    required_tools: Optional[list[str]] = None,
) -> DiscoveryReport:
    """
    Run discovery on the connected client and validate against the capability's discovery policy.
    """
    discovery = await client.discovery()
    policy = (capability_execution or {}).get("discovery") or {}
    await validate_discovery(
        discovery=discovery,
        required_tools=required_tools or [],
        policy=policy,
    )
    return discovery


async def get_validated_client_for_capability(
    *,
    capability: Dict[str, Any],
    manager: ClientManager[Any] | None = None,
) -> Tuple[ClientSignature, Any, DiscoveryReport]:
    """
    High-level helper:
      1) compute signature
      2) create/reuse MCP client
      3) run discovery + policy validation for the capability
    Returns (signature, client, discovery_report).
    """
    exec_cfg = capability.get("execution") or {}
    if exec_cfg.get("mode") != "mcp":
        raise ValueError("Capability must be an MCP execution to build an MCP client.")

    signature, client = await get_or_create_client(execution=exec_cfg, manager=manager)
    tools = required_tools_from_capability(capability)
    discovery = await ensure_discovery_and_validate(
        client=client,
        capability_execution=exec_cfg,
        required_tools=tools,
    )
    logger.info("MCP client ready: signature=%s, tools=%s", signature, tools)
    return signature, client, discovery