# services/planner-service/app/agent/execution_graph.py
"""
Execution Agent for planner-service.

Converts an approved PlannerSession plan into the conductor-service pack/playbook
format and runs it using conductor_core execution nodes.

Graph:
  plan_init → capability_executor → [plan_input_resolver → mcp_execution |
              llm_execution] → diagram_enrichment → narrative_enrichment → persist_run
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Optional, TypedDict
from uuid import uuid4

from langgraph.graph import StateGraph
from langgraph.graph.state import END

from conductor_core.models.run_models import (
    PlaybookRun, RunStatus, RunStrategy, StepState, StepStatus,
)
from conductor_core.nodes.capability_executor import capability_executor_node
from conductor_core.nodes.mcp_execution import mcp_execution_node
from conductor_core.nodes.llm_execution import llm_execution_node
from conductor_core.nodes.diagram_enrichment import diagram_enrichment_node
from conductor_core.nodes.narrative_enrichment import narrative_enrichment_node
from conductor_core.nodes.persist_run import persist_run_node
from conductor_core.llm.factory import get_agent_llm

from app.config import settings
from app.agent.nodes.plan_input_resolver import plan_input_resolver_node
from app.db.session_repository import SessionRepository
from app.db.run_repository import RunRepository
from app.cache.manifest_cache import get_manifest_cache
from app.events.rabbit import get_bus, EventPublisher
from app.clients.artifact_service import ArtifactServiceClient
from app.clients.workspace_manager import WorkspaceManagerClient
from app.events.stream import publish_to_session

logger = logging.getLogger("app.agent.execution_graph")


# ── State mirrors conductor-service GraphState ────────────────────────────────

class ExecutionState(TypedDict, total=False):
    request: Dict[str, Any]
    run: Dict[str, Any]
    pack: Dict[str, Any]
    artifact_kinds: Dict[str, Dict[str, Any]]
    agent_capabilities: list
    agent_capabilities_map: Dict[str, Dict[str, Any]]
    inputs_valid: bool
    input_errors: list
    input_fingerprint: Optional[str]
    step_idx: int
    current_step_id: Optional[str]
    phase: str
    dispatch: Annotated[Dict[str, Any], lambda left, right: right]
    logs: list
    validations: list
    started_at: str
    completed_at: Optional[str]
    staged_artifacts: list
    last_mcp_summary: Annotated[Dict[str, Any], lambda left, right: right]
    last_mcp_error: Annotated[Optional[str], lambda left, right: right]
    last_enrichment_summary: Annotated[Dict[str, Any], lambda left, right: right]
    last_enrichment_error: Annotated[Optional[str], lambda left, right: right]
    last_narrative_summary: Annotated[Dict[str, Any], lambda left, right: right]
    last_narrative_error: Annotated[Optional[str], lambda left, right: right]
    persist_summary: Dict[str, Any]
    # Cache for MCP tool schemas discovered via tools/list.
    # Key: capability_id → value: {tool_name: json_schema_dict}.
    discovered_tools: Annotated[Dict[str, Dict[str, Any]], lambda left, right: {**left, **right}]
    # Planner-specific
    session_id: Optional[str]
    run_inputs: Dict[str, Any]


# ── Plan-init node ────────────────────────────────────────────────────────────

def plan_init_node(*, session_repo: SessionRepository, run_repo: RunRepository, art_client: ArtifactServiceClient):
    """
    Converts an approved PlannerSession into conductor-service state format.
    Creates a PlaybookRun document and initializes the execution state.
    """
    async def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        session_id = state.get("session_id")
        workspace_id = state.get("workspace_id", "")
        strategy = state.get("strategy", RunStrategy.BASELINE.value)

        try:
            session = await session_repo.get_or_raise(session_id)
        except Exception as e:
            logger.error("[plan_init] session load failed: %s", e)
            return {"inputs_valid": False, "input_errors": [str(e)]}

        # Load full capability objects from cache
        cache = get_manifest_cache()
        capabilities = []
        for step in session.plan:
            if not step.enabled:
                continue
            cap = await cache.get_capability(step.capability_id)
            if cap:
                capabilities.append(cap)
            else:
                logger.warning("[plan_init] capability not found: %s", step.capability_id)

        # Build playbook (maps plan steps to conductor-service step format)
        enabled_steps = [s for s in session.plan if s.enabled]
        playbook_steps = []
        for i, ps in enumerate(enabled_steps):
            playbook_steps.append({
                "id": ps.step_id or f"step-{i}",
                "capability_id": ps.capability_id,
                "name": ps.title,
                "description": ps.description or ps.title,
                "inputs": ps.inputs or {},
                "order": i,
            })

        playbook_id = session_id  # use session_id as playbook_id
        pack = {
            "capabilities": capabilities,
            "playbooks": [{"id": playbook_id, "steps": playbook_steps}],
        }

        # Load diagram MCP agent capability — platform-level service, config-driven.
        # Build directly from settings so it is always available regardless of whether
        # cap.diagram.mermaid is registered in the capability registry.
        mermaid_cap: Dict[str, Any] = {
            "id": "cap.diagram.mermaid",
            "name": "Generate Mermaid Diagrams from Artifact JSON",
            "execution": {
                "mode": "mcp",
                "transport": {
                    "kind": "http",
                    "base_url": settings.diagram_mcp_base_url,
                    "headers": {"host": "localhost:8001"},
                    "protocol_path": settings.diagram_mcp_path,
                    "verify_tls": False,
                    "timeout_sec": settings.diagram_mcp_timeout_sec,
                },
                "tool_name": "diagram.mermaid.generate",
            },
        }
        agent_caps = [mermaid_cap]
        agent_caps_map: Dict[str, Any] = {"cap.diagram.mermaid": mermaid_cap}
        logger.info("[plan_init] diagram_mcp base=%s", settings.diagram_mcp_base_url)

        # Pre-fetch artifact kind specs so llm_execution can produce structured output
        produces_kinds: List[str] = []
        for cap in capabilities:
            for k in (cap.get("produces_kinds") or []):
                if k not in produces_kinds:
                    produces_kinds.append(k)

        kinds_map: Dict[str, Any] = {}
        if produces_kinds:
            async def _fetch(kind_id: str):
                data = await art_client.get_kind(kind_id)
                return kind_id, data

            results = await asyncio.gather(*[_fetch(k) for k in produces_kinds], return_exceptions=True)
            for res in results:
                if isinstance(res, Exception):
                    logger.warning("[plan_init] kind fetch failed: %s", res)
                else:
                    kind_id, data = res
                    if data:
                        kinds_map[kind_id] = data
            logger.info("[plan_init] artifact_kinds fetched=%d/%d", len(kinds_map), len(produces_kinds))

        # Resolve strategy: honour the frontend-supplied value (baseline or delta)
        run_strategy = RunStrategy.BASELINE
        if strategy and strategy.lower() == RunStrategy.DELTA.value:
            run_strategy = RunStrategy.DELTA

        # Transition the existing planner_runs document (created at planning time) to execution state
        run_inputs = state.get("run_inputs") or {}
        execution_steps = [
            StepState(step_id=s["id"], capability_id=s["capability_id"], name=s.get("name"))
            for s in playbook_steps
        ]
        effective_workspace = workspace_id or str(session.workspace_id)

        run_id_str = await run_repo.init_execution(
            session_id,
            steps=execution_steps,
            strategy=run_strategy,
            workspace_id=effective_workspace,
        )

        # Fallback: if no planning-phase doc exists, create a full PlaybookRun
        if not run_id_str:
            run_id_str = str(uuid4())
            run = PlaybookRun(
                run_id=run_id_str,
                workspace_id=effective_workspace,
                session_id=session_id,
                strategy=run_strategy,
                status=RunStatus.RUNNING,
                steps=execution_steps,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            await run_repo.create_run(run)

        await session_repo.set_active_run(session_id, run_id_str)

        # Build a PlaybookRun object for downstream nodes
        run = PlaybookRun(
            run_id=run_id_str,
            workspace_id=effective_workspace,
            session_id=session_id,
            strategy=run_strategy,
            status=RunStatus.RUNNING,
            steps=execution_steps,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        request = {
            "playbook_id": playbook_id,
            "inputs": run_inputs,  # user-confirmed form values from /run (ADR-006)
            "strategy": strategy,
            "workspace_id": effective_workspace,
            "llm_config": {},
        }

        logger.info("[plan_init] initialized run_id=%s steps=%d", run_id_str, len(playbook_steps))

        # Notify WebSocket
        publish_to_session(session_id, {
            "type": "execution.run_created",
            "session_id": session_id,
            "run_id": run_id_str,
            "step_count": len(playbook_steps),
            "at": datetime.now(timezone.utc).isoformat(),
        })

        return {
            "request": request,
            "run": run.model_dump(mode="json"),
            "pack": pack,
            "artifact_kinds": kinds_map,
            "agent_capabilities": agent_caps,
            "agent_capabilities_map": agent_caps_map,
            "inputs_valid": True,
            "input_errors": [],
            "input_fingerprint": None,
            "step_idx": 0,
            "current_step_id": None,
            "phase": "discover",
            "dispatch": {},
            "logs": [],
            "validations": [],
            "started_at": datetime.now(timezone.utc).isoformat(),
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

    return _node


# ── Graph builder ─────────────────────────────────────────────────────────────

async def _build_execution_graph(
    *,
    session_repo: SessionRepository,
    run_repo: RunRepository,
    art_client: ArtifactServiceClient,
    workspace_client: WorkspaceManagerClient,
):
    llm = await get_agent_llm(settings.planner_llm_config_ref or None)
    publisher = EventPublisher(bus=get_bus())

    graph = StateGraph(ExecutionState)

    graph.add_node("plan_init", plan_init_node(session_repo=session_repo, run_repo=run_repo, art_client=art_client))
    graph.add_node("capability_executor", capability_executor_node(runs_repo=run_repo, publisher=publisher, skip_diagram=settings.skip_diagram, skip_narrative=settings.skip_narrative))
    graph.add_node("mcp_input_resolver", plan_input_resolver_node(runs_repo=run_repo, llm=llm))
    graph.add_node("mcp_execution", mcp_execution_node(runs_repo=run_repo))
    graph.add_node("llm_execution", llm_execution_node(runs_repo=run_repo))
    graph.add_node("diagram_enrichment", diagram_enrichment_node(runs_repo=run_repo))
    graph.add_node("narrative_enrichment", narrative_enrichment_node(runs_repo=run_repo, llm=llm))
    graph.add_node("persist_run", persist_run_node(runs_repo=run_repo, art_client=art_client, workspace_client=workspace_client, publisher=publisher))

    graph.set_entry_point("plan_init")
    graph.add_edge("plan_init", "capability_executor")
    graph.add_edge("mcp_input_resolver", "mcp_execution")

    return graph.compile()


# ── Public function ───────────────────────────────────────────────────────────

async def run_execution_plan(
    *,
    session_id: str,
    strategy: str,
    workspace_id: str,
    run_inputs: Dict[str, Any],
    session_repo: SessionRepository,
    run_repo: RunRepository,
) -> str:
    """
    Build and run the execution graph for an approved plan.
    Returns the run_id of the created run.
    """
    art_client = ArtifactServiceClient()
    workspace_client = WorkspaceManagerClient()
    compiled = await _build_execution_graph(
        session_repo=session_repo,
        run_repo=run_repo,
        art_client=art_client,
        workspace_client=workspace_client,
    )

    initial_state: Dict[str, Any] = {
        "session_id": session_id,
        "workspace_id": workspace_id,
        "strategy": strategy,
        "run_inputs": run_inputs,
    }

    final_state = await compiled.ainvoke(
        initial_state,
        config={"recursion_limit": 256},
    )

    run_doc = final_state.get("run") or {}
    return run_doc.get("run_id", "")
