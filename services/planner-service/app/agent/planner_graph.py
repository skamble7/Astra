# services/planner-service/app/agent/planner_graph.py
"""
Planner Agent LangGraph graph.

Graph flow:
  session_init → planner_agent → plan_persist → END
                      ↑               (skipped on session_init error)
  (agentic loop with tool calls runs inside planner_agent node)

The planner_agent node runs a self-contained ReAct-style loop using LangChain
tool calling — no separate intent_resolver or capability_selector nodes needed.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import StateGraph
from langgraph.graph.state import END

from app.db.session_repository import SessionRepository
from app.cache.manifest_cache import get_manifest_cache
from app.agent.nodes.session_init import session_init_node
from app.agent.nodes.plan_approved import plan_approved_node
from app.agent.planner_agent import planner_agent_node

logger = logging.getLogger("app.agent.planner_graph")


# ── State ─────────────────────────────────────────────────────────────────────

class PlannerState(TypedDict, total=False):
    session_id: str
    org_id: str
    workspace_id: str
    messages: List[Dict[str, Any]]          # full chat history from session
    current_message: str                     # latest user message (trigger for this turn)
    existing_plan: List[Dict[str, Any]]      # current plan loaded from session
    draft_plan: List[Dict[str, Any]]         # plan after agent run (may be unchanged)
    response_message: str                    # markdown response for the chat pane
    intent: Dict[str, Any]                   # minimal intent metadata (for session update)
    status: str
    error: Optional[str]


# ── Graph builder ─────────────────────────────────────────────────────────────

def _build_planner_graph(session_repo: SessionRepository):
    cache = get_manifest_cache()

    graph = StateGraph(PlannerState)

    graph.add_node("session_init", session_init_node(session_repo=session_repo))
    graph.add_node("planner_agent", planner_agent_node(cache=cache))
    graph.add_node("plan_persist", plan_approved_node(session_repo=session_repo))

    graph.set_entry_point("session_init")

    def route_after_init(state: PlannerState) -> str:
        if state.get("error"):
            return END
        return "planner_agent"

    graph.add_conditional_edges("session_init", route_after_init)
    graph.add_edge("planner_agent", "plan_persist")
    graph.add_edge("plan_persist", END)

    return graph.compile()


# ── Public invoke function ────────────────────────────────────────────────────

async def invoke_planner(*, session_id: str, user_message: str) -> Dict[str, Any]:
    """
    Invoke the planner agent for one user message turn.
    Returns the final state dict (keys: draft_plan, response_message, status, …).
    """
    session_repo = SessionRepository()

    try:
        compiled = _build_planner_graph(session_repo)
    except Exception as e:
        logger.exception("Failed to build planner graph: %s", e)
        return {"response_message": f"Planner unavailable: {e}", "status": "failed"}

    try:
        final_state = await compiled.ainvoke(
            {
                "session_id": session_id,
                "current_message": user_message,
                "existing_plan": [],
            },
            config={"recursion_limit": 32},
        )
        return dict(final_state)
    except Exception as e:
        logger.exception("Planner graph invocation failed session=%s: %s", session_id, e)
        return {"response_message": f"Error during planning: {e}", "status": "failed"}
