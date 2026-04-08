# services/conductor-service/app/agent/graph.py
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, TypedDict, Annotated

from langgraph.graph import StateGraph
from langgraph.graph.state import END

from app.clients.artifact_service import ArtifactServiceClient
from app.clients.capability_service import CapabilityServiceClient
from app.clients.workspace_manager import WorkspaceManagerClient
from app.db.run_repository import RunRepository
from conductor_core.models.run_models import PlaybookRun

from app.agent.nodes.input_resolver import input_resolver_node
from conductor_core.nodes.capability_executor import capability_executor_node
from conductor_core.nodes.mcp_input_resolver import mcp_input_resolver_node
from conductor_core.nodes.mcp_execution import mcp_execution_node
from conductor_core.nodes.llm_execution import llm_execution_node
from conductor_core.nodes.persist_run import persist_run_node
from conductor_core.nodes.diagram_enrichment import diagram_enrichment_node
from conductor_core.nodes.narrative_enrichment import narrative_enrichment_node

from conductor_core.llm.factory import get_agent_llm
from app.events.rabbit import get_bus, EventPublisher
from app.config import settings


class GraphState(TypedDict, total=False):
    request: Dict[str, Any]
    run: Dict[str, Any]
    pack: Dict[str, Any]
    artifact_kinds: Dict[str, Dict[str, Any]]
    # NEW: keep agent-side capabilities available for enrichment
    agent_capabilities: list[Dict[str, Any]]
    agent_capabilities_map: Dict[str, Dict[str, Any]]

    inputs_valid: bool
    input_errors: list[str]
    input_fingerprint: Optional[str]
    step_idx: int
    current_step_id: Optional[str]
    phase: str  # "discover" | "enrich" | "narrative_enrich"
    # Use Annotated with reducer to allow multiple writes per step (capability_executor -> mcp_input_resolver)
    dispatch: Annotated[Dict[str, Any], lambda left, right: right]
    logs: list[str]
    validations: list[Dict[str, Any]]
    started_at: str
    completed_at: Optional[str]
    staged_artifacts: list[Dict[str, Any]]
    # These fields can be written by multiple nodes in the same step, use Annotated to take latest value
    last_mcp_summary: Annotated[Dict[str, Any], lambda left, right: right]
    last_mcp_error: Annotated[Optional[str], lambda left, right: right]
    last_enrichment_summary: Annotated[Dict[str, Any], lambda left, right: right]
    last_enrichment_error: Annotated[Optional[str], lambda left, right: right]
    last_narrative_summary: Annotated[Dict[str, Any], lambda left, right: right]
    last_narrative_error: Annotated[Optional[str], lambda left, right: right]
    persist_summary: Dict[str, Any]
    # Cache for MCP tool schemas discovered via tools/list.
    # Key: capability_id → value: {tool_name: json_schema_dict}.
    # Merged across steps so each cap_id is only fetched once per run.
    discovered_tools: Annotated[Dict[str, Dict[str, Any]], lambda left, right: {**left, **right}]


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def sha256_fingerprint(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


@dataclass
class ConductorGraph:
    runs_repo: RunRepository
    cap_client: CapabilityServiceClient
    art_client: ArtifactServiceClient
    workspace_client: WorkspaceManagerClient

    async def build(self, llm_config_ref: Optional[str] = None):
        """
        Build the conductor graph with optional per-request LLM config ref override.
        """
        graph = StateGraph(GraphState)

        # Build agent LLM via ConfigForge
        agent_llm = await get_agent_llm(llm_config_ref)

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
                publisher=EventPublisher(bus=get_bus()),
                skip_diagram=settings.skip_diagram,
                skip_narrative=settings.skip_narrative,
            ),
        )

        graph.add_node(
            "mcp_input_resolver",
            mcp_input_resolver_node(
                runs_repo=self.runs_repo,
                llm=agent_llm,
            ),
        )

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

        # Enrichment now uses runs_repo (for audits)
        graph.add_node(
            "diagram_enrichment",
            diagram_enrichment_node(
                runs_repo=self.runs_repo,
            ),
        )

        graph.add_node(
            "narrative_enrichment",
            narrative_enrichment_node(
                runs_repo=self.runs_repo,
                llm=agent_llm,
            ),
        )

        graph.add_node(
            "persist_run",
            persist_run_node(
                runs_repo=self.runs_repo,
                art_client=self.art_client,
                workspace_client=self.workspace_client,
                publisher=EventPublisher(bus=get_bus()),
            ),
        )

        # Edges
        graph.set_entry_point("input_resolver")
        graph.add_edge("input_resolver", "capability_executor")

        def route_from_capability_executor(state: GraphState):
            phase = state.get("phase") or "discover"
            dispatch = state.get("dispatch") or {}
            cap = dispatch.get("capability") or {}
            step = dispatch.get("step") or None

            if phase == "enrich" and state.get("current_step_id"):
                return "diagram_enrichment"

            if phase == "narrative_enrich" and state.get("current_step_id"):
                return "narrative_enrichment"

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
        graph.add_edge("diagram_enrichment", "capability_executor")
        graph.add_edge("narrative_enrichment", "capability_executor")

        return graph.compile()


async def run_input_bootstrap(
    *,
    runs_repo: RunRepository,
    cap_client: CapabilityServiceClient,
    art_client: ArtifactServiceClient,
    workspace_client: WorkspaceManagerClient,
    start_request: Dict[str, Any],
    run_doc: PlaybookRun,
) -> Dict[str, Any]:
    # Extract optional per-request LLM config ref
    llm_config = start_request.get("llm_config") or {}
    llm_config_ref = llm_config.get("llm_config_ref") if isinstance(llm_config, dict) else None

    compiled = await ConductorGraph(
        runs_repo=runs_repo,
        cap_client=cap_client,
        art_client=art_client,
        workspace_client=workspace_client,
    ).build(llm_config_ref=llm_config_ref)

    now = datetime.now(timezone.utc).isoformat()

    initial_state: Dict[str, Any] = {
        "request": start_request,
        "run": run_doc.model_dump(mode="json"),
        "artifact_kinds": {},
        # NEW: seed agent capability slots so input_resolver can populate them
        "agent_capabilities": [],
        "agent_capabilities_map": {},
        "inputs_valid": False,
        "input_errors": [],
        "input_fingerprint": None,
        "step_idx": 0,
        "current_step_id": None,
        "phase": "discover",
        "dispatch": {},
        "logs": [],
        "validations": [],
        "started_at": now,
        "completed_at": None,
        "staged_artifacts": [],
        "last_mcp_summary": {},
        "last_mcp_error": None,
        "last_enrichment_summary": {},
        "last_enrichment_error": None,
        "last_narrative_summary": {},
        "last_narrative_error": None,
        "persist_summary": {},
        "discovered_tools": {},
    }

    # >>> CHANGE: raise recursion limit to handle long playbooks w/ enrichment passes
    final_state: Dict[str, Any] = await compiled.ainvoke(
        initial_state,
        config={"recursion_limit": 256},
    )
    return final_state