# services/capability-service/app/mcp_schema.py
"""
Live MCP schema resolution: connects to an MCP server, calls tools/list,
and returns the JSON Schema for the target tool.

Uses the official mcp SDK (mcp>=1.15,<2) with streamable HTTP transport.
No LLM or langchain dependency required.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("app.mcp_schema")


async def resolve_mcp_input_schema(
    *,
    transport: Dict[str, Any],
    tool_name: str,
) -> Optional[Dict[str, Any]]:
    """
    Connect to the MCP server described by `transport`, call tools/list,
    and return { json_schema, tool_name, tool_description } for the target tool.

    Returns None if the server is unreachable or the tool is not found.
    """
    base_url = str(transport.get("base_url") or "").rstrip("/")
    headers: Dict[str, str] = dict(transport.get("headers") or {})

    if not base_url:
        logger.warning("[mcp_schema] transport missing base_url")
        return None

    # Use streamable HTTP at /mcp (standard for all our MCP servers)
    url = f"{base_url}/mcp"

    try:
        from mcp.client.streamable_http import streamablehttp_client
        from mcp.client.session import ClientSession

        async with streamablehttp_client(url, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                tools = result.tools or []

                # Pick by name or fall back to first tool
                target = None
                for t in tools:
                    if t.name == tool_name:
                        target = t
                        break
                if target is None and tools:
                    target = tools[0]

                if target is None:
                    logger.warning("[mcp_schema] no tools found at %s", url)
                    return None

                return {
                    "json_schema": target.inputSchema or {},
                    "tool_name": target.name,
                    "tool_description": target.description or "",
                }

    except Exception as exc:
        logger.warning("[mcp_schema] tools/list failed url=%s err=%s", url, exc)
        return None
