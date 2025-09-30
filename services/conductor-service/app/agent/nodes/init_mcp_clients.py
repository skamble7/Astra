# services/conductor-service/app/agent/nodes/init_mcp_clients.py
from __future__ import annotations

import logging
from typing import Any, Dict

from app.mcp_host.factory import get_validated_client_for_capability

logger = logging.getLogger("app.agent.nodes.mcp_init")


async def init_mcp_clients(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    For each MCP capability referenced by the playbook, create/reuse a client and run discovery validation once.
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

        sig, client, discovery = await get_validated_client_for_capability(capability=cap)
        state["mcp"]["clients"][cap_id] = {"signature": sig, "client": client}
        state["mcp"]["discovery_reports"][cap_id] = discovery

    logger.info("Initialized %d MCP clients", len(state["mcp"]["clients"]))
    return state