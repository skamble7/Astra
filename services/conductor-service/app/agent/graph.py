# services/conductor-service/app/agent/graph.py
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from langgraph.graph import END, StateGraph

from app.agent.nodes.ingest_request import ingest_request
from app.agent.nodes.resolve_pack_and_validate_inputs import resolve_pack_and_validate_inputs
from app.agent.nodes.prefetch_kinds_and_index import prefetch_kinds_and_index
from app.agent.nodes.init_mcp_clients import init_mcp_clients
from app.agent.nodes.mark_run_started import mark_run_started
from app.agent.nodes.execute_steps import execute_steps
from app.agent.nodes.compute_diffs_vs_baseline import compute_diffs_vs_baseline
from app.agent.nodes.persist_results import persist_results
from app.agent.nodes.publish_summary import publish_summary
from app.agent.nodes.mark_run_completed import mark_run_completed
from app.agent.nodes.handle_error import handle_error

logger = logging.getLogger("app.agent.graph")


def _route(next_node: str):
    """Return a router fn that jumps to handle_error if state.error is set, else to next_node."""
    def _fn(state: Dict[str, Any]) -> str:
        return "handle_error" if state.get("error") else next_node
    return _fn


def build_graph() -> StateGraph:
    """
    Builds the LangGraph state machine for a run.
    State is a plain dict carrying everything the nodes need.
    """
    g = StateGraph(dict)

    # register nodes
    g.add_node("ingest_request", ingest_request)
    g.add_node("resolve_pack_and_validate_inputs", resolve_pack_and_validate_inputs)
    g.add_node("prefetch_kinds_and_index", prefetch_kinds_and_index)
    g.add_node("init_mcp_clients", init_mcp_clients)
    g.add_node("mark_run_started", mark_run_started)
    g.add_node("execute_steps", execute_steps)
    g.add_node("compute_diffs_vs_baseline", compute_diffs_vs_baseline)
    g.add_node("persist_results", persist_results)
    g.add_node("publish_summary", publish_summary)
    g.add_node("mark_run_completed", mark_run_completed)
    g.add_node("handle_error", handle_error)

    # happy-path with conditional error routing
    g.add_conditional_edges("ingest_request", _route("resolve_pack_and_validate_inputs"),
                            {"resolve_pack_and_validate_inputs": "resolve_pack_and_validate_inputs",
                             "handle_error": "handle_error"})

    g.add_conditional_edges("resolve_pack_and_validate_inputs", _route("prefetch_kinds_and_index"),
                            {"prefetch_kinds_and_index": "prefetch_kinds_and_index",
                             "handle_error": "handle_error"})

    g.add_conditional_edges("prefetch_kinds_and_index", _route("init_mcp_clients"),
                            {"init_mcp_clients": "init_mcp_clients",
                             "handle_error": "handle_error"})

    g.add_conditional_edges("init_mcp_clients", _route("mark_run_started"),
                            {"mark_run_started": "mark_run_started",
                             "handle_error": "handle_error"})

    g.add_conditional_edges("mark_run_started", _route("execute_steps"),
                            {"execute_steps": "execute_steps",
                             "handle_error": "handle_error"})

    g.add_conditional_edges("execute_steps", _route("compute_diffs_vs_baseline"),
                            {"compute_diffs_vs_baseline": "compute_diffs_vs_baseline",
                             "handle_error": "handle_error"})

    g.add_conditional_edges("compute_diffs_vs_baseline", _route("persist_results"),
                            {"persist_results": "persist_results",
                             "handle_error": "handle_error"})

    g.add_conditional_edges("persist_results", _route("publish_summary"),
                            {"publish_summary": "publish_summary",
                             "handle_error": "handle_error"})

    g.add_conditional_edges("publish_summary", _route("mark_run_completed"),
                            {"mark_run_completed": "mark_run_completed",
                             "handle_error": "handle_error"})

    g.add_edge("mark_run_completed", END)

    g.set_entry_point("ingest_request")
    return g


# Build & compile once at import time
_graph = build_graph().compile()


async def run_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Drives the compiled LangGraph. Returns the final state after END.
    """
    async for _ in _graph.astream(state):
        pass
    return state


def spawn_agent_task(initial_state: Dict[str, Any]) -> asyncio.Task:
    """
    Fire-and-forget helper used by the API route to start a run asynchronously.
    """
    return asyncio.create_task(
        run_agent(initial_state),
        name=f"run-agent-{initial_state.get('run', {}).get('run_id')}",
    )


__all__ = ["spawn_agent_task", "run_agent"]