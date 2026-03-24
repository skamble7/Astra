from __future__ import annotations

import base64
import logging
import os
from typing import Optional

from fastapi import HTTPException

from conductor_core.mcp.mcp_client import MCPConnection, MCPTransportConfig

from app.config import settings
from app.models.mcp_onboarding_models import (
    CapabilityOnboardingDoc,
    DiscoveredTool,
    ServerConnectionConfig,
)
from app.services.llm_inferencer import LLMInferencer

logger = logging.getLogger("app.services.mcp_inspector")


def _rewrite_localhost(url: str, headers: dict) -> tuple[str, dict]:
    """
    When running inside Docker, 'localhost' in a user-supplied MCP URL refers
    to the container itself, not the host machine. Rewrites the URL to
    MCP_LOCALHOST_ALIAS (typically 'host.docker.internal') so the TCP connection
    reaches the Docker host, then injects a `host` header with the original
    hostname so the MCP server's virtual-host check passes (avoids 421).
    Does nothing when MCP_LOCALHOST_ALIAS is unset (local dev without Docker).
    """
    alias = settings.mcp_localhost_alias
    if not alias:
        return url, headers

    rewritten = url
    original_host: Optional[str] = None

    for local in ("localhost", "127.0.0.1"):
        marker = f"://{local}:"
        if marker in url:
            # Extract "localhost:<port>" before rewriting so we can set Host header
            port_start = url.index(marker) + len(marker)
            port_end = url.find("/", port_start)
            port = url[port_start:] if port_end == -1 else url[port_start:port_end]
            original_host = f"{local}:{port}"
            rewritten = url.replace(marker, f"://{alias}:")
            break

    if rewritten != url:
        logger.info("[MCPInspector] Rewrote MCP URL: %s → %s", url, rewritten)
        # Inject Host header so the server accepts the request (avoids 421)
        # Only set if caller hasn't already provided one
        merged = dict(headers)
        if "host" not in {k.lower() for k in merged}:
            merged["host"] = original_host
            logger.info("[MCPInspector] Injected Host header: %s", original_host)
        return rewritten, merged

    return url, headers


def _resolve_headers(server: ServerConnectionConfig) -> dict:
    """
    Merge explicit headers from the server config with any auth headers derived
    from the AuthSpec. AuthSpec values are env-var alias names — values are
    read from the environment at call time.
    """
    headers = dict(server.headers)
    auth = server.auth

    if auth is None or auth.method == "none":
        return headers

    if auth.method == "bearer" and auth.alias_token:
        token = os.getenv(auth.alias_token, "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        else:
            logger.warning(
                "Bearer token alias '%s' not found in environment", auth.alias_token
            )

    elif auth.method == "api_key" and auth.alias_key:
        key = os.getenv(auth.alias_key, "")
        if key:
            headers["X-API-Key"] = key
        else:
            logger.warning(
                "API key alias '%s' not found in environment", auth.alias_key
            )

    elif auth.method == "basic" and auth.alias_user and auth.alias_password:
        user = os.getenv(auth.alias_user, "")
        password = os.getenv(auth.alias_password, "")
        if user and password:
            cred = base64.b64encode(f"{user}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {cred}"
        else:
            logger.warning(
                "Basic auth aliases '%s'/'%s' not fully resolved from environment",
                auth.alias_user,
                auth.alias_password,
            )

    return headers


class MCPInspector:
    """
    Connects to an MCP server, discovers available tools, and optionally
    triggers LLM inference on the selected tool.
    """

    async def resolve(
        self,
        server: ServerConnectionConfig,
        tool_name: Optional[str],
    ) -> CapabilityOnboardingDoc:
        headers = _resolve_headers(server)
        base_url, headers = _rewrite_localhost(server.base_url, headers)

        cfg = MCPTransportConfig(
            kind="http",
            base_url=base_url,
            headers=headers,
            protocol_path=server.protocol_path,
            verify_tls=server.verify_tls,
            timeout_sec=server.timeout_seconds,
        )

        logger.info(
            "[MCPInspector] Connecting to %s (protocol_path=%s)",
            server.base_url,
            server.protocol_path,
        )

        conn = await MCPConnection.connect(cfg)
        try:
            raw_tools = await conn.list_tools_raw()
        finally:
            await conn.aclose()

        if not raw_tools:
            raise HTTPException(
                status_code=422,
                detail="MCP server returned no tools. Verify the server is running and the protocol path is correct.",
            )

        available = [
            DiscoveredTool(
                name=name,
                description=(input_schema or {}).get("description"),
                input_schema=input_schema or {},
                output_schema=output_schema,
            )
            for name, input_schema, output_schema in raw_tools
        ]

        logger.info(
            "[MCPInspector] Discovered %d tool(s): %s",
            len(available),
            ", ".join(t.name for t in available),
        )

        # Multi-tool server with no selection yet — return picker state
        if tool_name is None and len(available) > 1:
            logger.info("[MCPInspector] Multiple tools found, returning picker state")
            return CapabilityOnboardingDoc(
                server=server,
                available_tools=available,
                status="discovered",
            )

        # Select the target tool
        if tool_name is not None:
            matches = [t for t in available if t.name == tool_name]
            if not matches:
                raise HTTPException(
                    status_code=404,
                    detail=f"Tool '{tool_name}' not found on server. Available: {[t.name for t in available]}",
                )
            selected = matches[0]
        else:
            selected = available[0]

        logger.info("[MCPInspector] Selected tool: %s — running LLM inference", selected.name)

        inferencer = LLMInferencer()
        inferred = await inferencer.infer(selected)

        return CapabilityOnboardingDoc(
            server=server,
            selected_tool=selected,
            available_tools=available,
            inferred=inferred,
            status="inferred",
        )
