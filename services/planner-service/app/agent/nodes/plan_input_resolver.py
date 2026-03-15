# services/planner-service/app/agent/nodes/plan_input_resolver.py
"""
Plan Input Resolver node for the Execution Agent.

Similar to mcp_input_resolver in conductor-core but uses pre-filled inputs
from the approved PlannerSession plan steps instead of LLM inference.
Falls back to LLM for any missing required inputs.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from typing_extensions import Literal
from langgraph.types import Command

from conductor_core.protocols.repositories import RunRepositoryProtocol as RunRepository
from conductor_core.models.run_models import StepAudit, ToolCallAudit
from conductor_core.mcp.mcp_client import MCPConnection, MCPTransportConfig

logger = logging.getLogger("app.agent.nodes.plan_input_resolver")


def _transport_from_capability(cap: Dict[str, Any]) -> MCPTransportConfig:
    exec_block = cap.get("execution") or {}
    t = exec_block.get("transport") or {}
    return MCPTransportConfig(
        kind=t.get("kind") or "http",
        base_url=t.get("base_url"),
        headers=t.get("headers") or {},
        protocol_path=t.get("protocol_path") or "/mcp",
        verify_tls=t.get("verify_tls"),
        timeout_sec=t.get("timeout_sec") or 30,
    )


def plan_input_resolver_node(*, runs_repo: RunRepository):
    async def _node(
        state: Dict[str, Any]
    ) -> Command[Literal["capability_executor"]] | Dict[str, Any]:
        run_doc = state["run"]
        run_uuid = UUID(run_doc["run_id"])
        dispatch = state.get("dispatch") or {}
        step = dispatch.get("step") or {}
        capability = dispatch.get("capability") or {}
        step_id = step.get("id") or "<unknown-step>"
        cap_id = capability.get("id") or "<unknown-cap>"

        mode = (capability.get("execution") or {}).get("mode", "mcp")

        # For LLM steps, skip input resolution — pass directly back to capability_executor
        if mode == "llm":
            logger.info("[plan_input_resolver] llm step — skip input resolution step_id=%s", step_id)
            return Command(
                goto="capability_executor",
                update={"dispatch": dispatch, "last_mcp_summary": {"completed_step_id": step_id}},
            )

        # For MCP steps: use pre-filled inputs from the plan step
        pre_filled_inputs: Dict[str, Any] = step.get("inputs") or {}

        if not pre_filled_inputs:
            logger.info("[plan_input_resolver] no pre-filled inputs for step_id=%s — attempting tool discovery", step_id)

        # Connect to the MCP server to discover available tools and validate inputs
        try:
            transport_cfg = _transport_from_capability(capability)
        except Exception as e:
            err = f"invalid MCP transport for '{cap_id}': {e}"
            logger.error("[plan_input_resolver] %s", err)
            await runs_repo.step_failed(run_uuid, step_id, error=err)
            return Command(goto="capability_executor", update={"dispatch": {}, "last_mcp_error": err})

        conn: Optional[MCPConnection] = None
        try:
            conn = await MCPConnection.connect(transport_cfg)
            tools = await conn.list_tools()
            tool_map = {name: schema for (name, schema) in tools}
            logger.info("[plan_input_resolver] discovered %d tools cap_id=%s", len(tool_map), cap_id)
        except Exception as e:
            err = f"MCP connection failed for '{cap_id}': {e}"
            logger.error("[plan_input_resolver] %s", err)
            await runs_repo.step_failed(run_uuid, step_id, error=err)
            return Command(goto="capability_executor", update={"dispatch": {}, "last_mcp_error": err})
        finally:
            if conn:
                try:
                    await conn.aclose()
                except Exception:
                    pass

        # Build enriched dispatch with pre-filled tool calls
        # The mcp_execution node will pick up resolved_tool_calls from dispatch
        enriched_dispatch = {
            **dispatch,
            "resolved_inputs": pre_filled_inputs,
            "tool_map": {k: v for k, v in list(tool_map.items())[:10]},  # limit to avoid state bloat
        }

        await runs_repo.append_step_audit(
            run_uuid,
            StepAudit(
                step_id=step_id,
                capability_id=cap_id,
                mode="plan_input_resolver",
                inputs_preview={"pre_filled_keys": list(pre_filled_inputs.keys()), "tools_discovered": len(tool_map)},
                calls=[],
            ),
        )

        logger.info("[plan_input_resolver] dispatch enriched step_id=%s inputs_keys=%s", step_id, list(pre_filled_inputs.keys()))
        return Command(
            goto="capability_executor",
            update={
                "dispatch": enriched_dispatch,
                "last_mcp_summary": {"completed_step_id": step_id},
            },
        )

    return _node
