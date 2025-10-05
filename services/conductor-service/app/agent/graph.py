# services/conductor-service/app/agent/graph.py
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, TypedDict

from langgraph.graph import StateGraph
from langgraph.graph.state import END

from app.clients.artifact_service import ArtifactServiceClient
from app.clients.capability_service import CapabilityServiceClient
from app.db.run_repository import RunRepository
from app.models.run_models import PlaybookRun

from app.agent.nodes.input_resolver import input_resolver_node
from app.agent.nodes.capability_executor import capability_executor_node
from app.agent.nodes.mcp_input_resolver import mcp_input_resolver_node  # existing
from app.agent.nodes.mcp_execution import mcp_execution_node
from app.agent.nodes.llm_execution import llm_execution_node
from app.agent.nodes.persist_run import persist_run_node  # NEW

from app.llm.factory import get_agent_llm


class GraphState(TypedDict, total=False):
    request: Dict[str, Any]
    run: Dict[str, Any]
    pack: Dict[str, Any]
    artifact_kinds: Dict[str, Dict[str, Any]]
    inputs_valid: bool
    input_errors: list[str]
    input_fingerprint: Optional[str]
    step_idx: int
    current_step_id: Optional[str]
    dispatch: Dict[str, Any]
    logs: list[str]
    validations: list[Dict[str, Any]]
    started_at: str
    completed_at: Optional[str]
    staged_artifacts: list[Dict[str, Any]]
    last_mcp_summary: Dict[str, Any]
    last_mcp_error: Optional[str]
    persist_summary: Dict[str, Any]


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def sha256_fingerprint(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


@dataclass
class ConductorGraph:
    runs_repo: RunRepository
    cap_client: CapabilityServiceClient
    art_client: ArtifactServiceClient

    def build(self):
        graph = StateGraph(GraphState)

        agent_llm = get_agent_llm()

        graph.add_node(
            "input_resolver",
            input_resolver_node(
                runs_repo=self.runs_repo,
                cap_client=self.cap_client,
                art_client=self.art_client,
                sha256_fingerprint=sha256_fingerprint,
            ),
        )
        graph.add_node(
            "capability_executor",
            capability_executor_node(
                runs_repo=self.runs_repo,
            ),
        )

        # MCP input resolver
        graph.add_node(
            "mcp_input_resolver",
            mcp_input_resolver_node(
                runs_repo=self.runs_repo,
                llm=agent_llm,
            ),
        )

        # Execution nodes
        graph.add_node(
            "mcp_execution",
            mcp_execution_node(
                runs_repo=self.runs_repo,
            ),
        )
        graph.add_node(
            "llm_execution",
            llm_execution_node(
                runs_repo=self.runs_repo,
            ),
        )

        # NEW: persist_run (terminal writer)
        graph.add_node(
            "persist_run",
            persist_run_node(
                runs_repo=self.runs_repo,
            ),
        )

        # Edges
        graph.set_entry_point("input_resolver")
        graph.add_edge("input_resolver", "capability_executor")

        # Conditional routes from router when it doesn't explicitly Command-goto
        def route_from_capability_executor(state: GraphState):
            """
            Decide next hop after capability_executor:
            - If there's an active dispatch with a capability+step, route by mode.
            - If no dispatch, we assume router already decided to persist (it usually Command-goto's persist_run).
              As a safe default, end the graph.
            """
            dispatch = state.get("dispatch") or {}
            cap = dispatch.get("capability") or {}
            step = dispatch.get("step") or None

            if cap and step:
                mode = (cap.get("execution") or {}).get("mode")
                if mode == "mcp":
                    return "mcp_input_resolver"
                elif mode == "llm":
                    return "llm_execution"
                else:
                    return "capability_executor"

            return END

        graph.add_conditional_edges("capability_executor", route_from_capability_executor)

        graph.add_edge("mcp_input_resolver", "mcp_execution")
        graph.add_edge("mcp_execution", "capability_executor")
        graph.add_edge("llm_execution", "capability_executor")
        # persist_run returns a terminal dict; no edges needed.

        return graph.compile()


async def run_input_bootstrap(
    *,
    runs_repo: RunRepository,
    cap_client: CapabilityServiceClient,
    art_client: ArtifactServiceClient,
    start_request: Dict[str, Any],
    run_doc: PlaybookRun,
) -> Dict[str, Any]:
    compiled = ConductorGraph(
        runs_repo=runs_repo,
        cap_client=cap_client,
        art_client=art_client,
    ).build()

    now = datetime.now(timezone.utc).isoformat()

    initial_state: Dict[str, Any] = {
        "request": start_request,
        "run": run_doc.model_dump(mode="json"),
        "artifact_kinds": {},
        "inputs_valid": False,
        "input_errors": [],
        "input_fingerprint": None,
        "step_idx": 0,
        "current_step_id": None,
        "dispatch": {},
        "logs": [],
        "validations": [],
        "started_at": now,
        "completed_at": None,
        "staged_artifacts": [],
        "last_mcp_summary": {},
        "last_mcp_error": None,
        "persist_summary": {},
    }

    final_state: Dict[str, Any] = await compiled.ainvoke(initial_state)
    return final_state
