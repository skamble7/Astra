# services/planner-service/app/agent/planner_graph.py
"""
Planner Agent LangGraph graph.

Graph flow:
  session_init → intent_resolver → capability_selector → plan_builder
              → (conditional: clarification | plan_approved)

Uses MongoDB checkpointer so state persists between message invocations
(thread_id = session_id).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Annotated, Dict, List, Optional, TypedDict

from langgraph.graph import StateGraph
from langgraph.graph.state import END

from app.config import settings
from app.db.session_repository import SessionRepository
from app.cache.manifest_cache import get_manifest_cache
from app.agent.nodes.session_init import session_init_node
from app.agent.nodes.intent_resolver import intent_resolver_node
from app.agent.nodes.capability_selector import capability_selector_node
from app.agent.nodes.plan_builder import plan_builder_node
from app.agent.nodes.clarification import clarification_node
from app.agent.nodes.plan_approved import plan_approved_node

logger = logging.getLogger("app.agent.planner_graph")

_CONFIDENCE_THRESHOLD = float(os.getenv("PLANNER_CONFIDENCE_THRESHOLD", "0.65"))


# ── State ────────────────────────────────────────────────────────────────────

class PlannerState(TypedDict, total=False):
    session_id: str
    org_id: str
    workspace_id: str
    messages: List[Dict[str, Any]]          # full chat history
    current_message: str                     # latest user message
    intent: Dict[str, Any]                   # extracted intent
    candidate_capabilities: List[Dict[str, Any]]  # from manifest cache
    draft_plan: List[Dict[str, Any]]         # assembled plan steps
    confidence_score: float
    needs_clarification: bool
    clarification_question: str
    response_message: str
    status: str
    error: Optional[str]


# ── Graph builder ─────────────────────────────────────────────────────────────

async def _build_planner_graph(session_repo: SessionRepository):
    from conductor_core.llm.factory import get_agent_llm
    llm = await get_agent_llm(settings.planner_llm_config_ref or None)
    cache = get_manifest_cache()

    graph = StateGraph(PlannerState)

    graph.add_node("session_init", session_init_node(session_repo=session_repo))
    graph.add_node("intent_resolver", intent_resolver_node(llm=llm))
    graph.add_node("capability_selector", capability_selector_node(llm=llm, cache=cache))
    graph.add_node("plan_builder", plan_builder_node(llm=llm, cache=cache))
    graph.add_node("clarification", clarification_node(session_repo=session_repo))
    graph.add_node("plan_approved", plan_approved_node(session_repo=session_repo))

    graph.set_entry_point("session_init")
    graph.add_edge("session_init", "intent_resolver")
    graph.add_edge("intent_resolver", "capability_selector")
    graph.add_edge("capability_selector", "plan_builder")

    def route_after_plan_builder(state: PlannerState) -> str:
        if state.get("needs_clarification", False):
            return "clarification"
        return "plan_approved"

    graph.add_conditional_edges("plan_builder", route_after_plan_builder)
    graph.add_edge("clarification", END)
    graph.add_edge("plan_approved", END)

    return graph.compile()


# ── Public invoke function ────────────────────────────────────────────────────

async def invoke_planner(*, session_id: str, user_message: str) -> Dict[str, Any]:
    """
    Invoke the planner agent for one user message turn.
    Returns the final state dict.
    """
    session_repo = SessionRepository()

    try:
        compiled = await _build_planner_graph(session_repo)
    except Exception as e:
        logger.exception("Failed to build planner graph: %s", e)
        return {"response_message": f"Planner unavailable: {e}", "status": "failed"}

    try:
        final_state = await compiled.ainvoke(
            {
                "session_id": session_id,
                "current_message": user_message,
                "confidence_score": 0.0,
                "needs_clarification": False,
            },
            config={"recursion_limit": 64},
        )
        return dict(final_state)
    except Exception as e:
        logger.exception("Planner graph invocation failed session=%s: %s", session_id, e)
        return {"response_message": f"Error during planning: {e}", "status": "failed"}
