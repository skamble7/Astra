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

    # edges (happy path)
    g.add_edge("ingest_request", "resolve_pack_and_validate_inputs")
    g.add_edge("resolve_pack_and_validate_inputs", "prefetch_kinds_and_index")
    g.add_edge("prefetch_kinds_and_index", "init_mcp_clients")
    g.add_edge("init_mcp_clients", "mark_run_started")
    g.add_edge("mark_run_started", "execute_steps")
    g.add_edge("execute_steps", "compute_diffs_vs_baseline")
    g.add_edge("compute_diffs_vs_baseline", "persist_results")
    g.add_edge("persist_results", "publish_summary")
    g.add_edge("publish_summary", "mark_run_completed")
    g.add_edge("mark_run_completed", END)

    # error fan-in
    for n in [
        "ingest_request",
        "resolve_pack_and_validate_inputs",
        "prefetch_kinds_and_index",
        "init_mcp_clients",
        "mark_run_started",
        "execute_steps",
        "compute_diffs_vs_baseline",
        "persist_results",
        "publish_summary",
        "mark_run_completed",
    ]:
        g.add_edge(n, "handle_error")

    g.set_entry_point("ingest_request")
    return g


_graph = build_graph().compile()


async def run_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Entrypoint to execute the compiled LangGraph agent.
    `state` must at least include:
      - "request" (StartRunRequest.model_dump())
    """
    # LangGraph returns the final state after END.
    async for _ in _graph.astream(state):
        # streaming is available; here we just iterate to drive the graph
        pass
    return state


def spawn_agent_task(initial_state: Dict[str, Any]) -> asyncio.Task:
    """
    Fire-and-forget helper used by the API route to start a run asynchronously.
    """
    return asyncio.create_task(run_agent(initial_state), name=f"run-agent-{initial_state.get('run',{}).get('run_id')}")