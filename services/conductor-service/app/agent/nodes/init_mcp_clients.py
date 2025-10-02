# services/conductor-service/app/agent/nodes/init_mcp_clients.py
from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.mcp_host.official_client import build_client_from_capability
from app.mcp_host.discovery_validator import validate as validate_discovery

logger = logging.getLogger("app.agent.nodes.mcp_init")


def _required_tools_from_capability(cap: Dict[str, Any]) -> List[str]:
    tcalls = (cap.get("execution", {}).get("tool_calls") or [])
    return [tc.get("tool") for tc in tcalls if isinstance(tc, dict) and tc.get("tool")]


async def init_mcp_clients(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    For each MCP capability in the selected playbook:
      - build official client (SSE or stdio) per capability.transport
      - connect + initialize
      - run discovery once (and validate against capability policy)
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

        # build + connect
        client = await build_client_from_capability(cap)
        discovery = await client.discovery()

        # validate expected tools if requested
        policy = (exec_cfg.get("discovery") or {})
        expected = _required_tools_from_capability(cap)
        await validate_discovery(discovery=discovery, required_tools=expected, policy=policy)

        state["mcp"]["clients"][cap_id] = {"client": client}
        state["mcp"]["discovery_reports"][cap_id] = discovery

        logger.info(
            "MCP client ready for %s; tools=%s resources=%s",
            cap_id,
            discovery.get("tools"),
            len(discovery.get("resources", []) or []),
        )

    logger.info("Initialized %d MCP clients", len(state["mcp"]["clients"]))
    return state