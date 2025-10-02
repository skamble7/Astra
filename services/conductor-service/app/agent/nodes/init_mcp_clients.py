# services/conductor-service/app/agent/nodes/init_mcp_clients.py
from __future__ import annotations

import logging
from typing import Any, Dict

from app.mcp_host.official_client import build_stdio_client_from_capability

logger = logging.getLogger("app.agent.nodes.mcp_init")


async def init_mcp_clients(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    For each MCP capability in the selected playbook:
      - build official stdio client
      - connect + initialize
      - run discovery once
      - stash in state for execute_steps
    """
    cap_by_id = state["pack"]["capabilities_by_id"]
    playbook = state["pack"]["playbook"]

    for step in (playbook.get("steps") or []):
        cap_id = step["capability_id"]
        cap = cap_by_id.get(cap_id) or {}
        exec_cfg = cap.get("execution") or {}
        if exec_cfg.get("mode") != "mcp":
            continue

        if cap_id in state["mcp"]["clients"]:
            continue

        # Build client from capability transport (stdio)
        client = build_stdio_client_from_capability(cap)
        await client.connect()

        # Discovery
        discovery = await client.discovery()
        state["mcp"]["clients"][cap_id] = {"client": client}
        state["mcp"]["discovery_reports"][cap_id] = discovery

        logger.info("MCP client ready for %s; tools=%s", cap_id, discovery.get("tools"))

    logger.info("Initialized %d MCP clients", len(state["mcp"]["clients"]))
    return state