# services/planner-service/app/api/routers/session_routes.py
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger("app.api.routers.sessions")

from fastapi import APIRouter, HTTPException, BackgroundTasks

from app.db.session_repository import SessionRepository
from app.db.run_repository import RunRepository
from app.models.session_models import (
    PlannerSession,
    CreateSessionRequest,
    SendMessageRequest,
    UpdatePlanRequest,
    ApprovePlanRequest,
    RunRequest,
    SessionStatus,
    ChatMessage,
    MessageRole,
)
from app.agent.planner_graph import invoke_planner
from app.agent.execution_graph import run_execution_plan
from app.cache.manifest_cache import get_manifest_cache
from conductor_core.mcp.mcp_client import MCPConnection, MCPTransportConfig
from app.events.stream import publish_to_session
from app.events.rabbit import get_bus
from libs.astra_common.events import Service

router = APIRouter(prefix="/sessions", tags=["sessions"])
logger = logging.getLogger("app.api.sessions")


def _get_session_repo() -> SessionRepository:
    return SessionRepository()


def _get_run_repo() -> RunRepository:
    return RunRepository()


@router.post("", summary="Create a new planning session")
async def create_session(
    request: CreateSessionRequest,
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    repo = _get_session_repo()
    session = PlannerSession(
        org_id=request.org_id,
        workspace_id=request.workspace_id,
    )
    await repo.create(session)

    result = {"session_id": session.session_id, "status": session.status.value}

    # If initial message provided, kick off planning in background
    if request.initial_message:
        msg = ChatMessage(role=MessageRole.USER, content=request.initial_message)
        await repo.append_message(session.session_id, msg)
        background_tasks.add_task(
            _run_planner_bg,
            session.session_id,
            request.initial_message,
        )

    return result


@router.get("/{session_id}", summary="Get session state")
async def get_session(session_id: str) -> Dict[str, Any]:
    repo = _get_session_repo()
    session = await repo.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return session.model_dump(mode="json")


@router.post("/{session_id}/messages", summary="Send a user message to the Planner Agent")
async def send_message(
    session_id: str,
    request: SendMessageRequest,
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    repo = _get_session_repo()
    session = await repo.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    if session.status == SessionStatus.EXECUTING:
        raise HTTPException(status_code=409, detail="Session is currently executing a plan")

    msg = ChatMessage(role=MessageRole.USER, content=request.content)
    await repo.append_message(session_id, msg)

    background_tasks.add_task(_run_planner_bg, session_id, request.content)

    return {"session_id": session_id, "status": "processing", "message": "Planner agent invoked"}


@router.get("/{session_id}/plan", summary="Get current plan")
async def get_plan(session_id: str) -> Dict[str, Any]:
    repo = _get_session_repo()
    session = await repo.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return {
        "session_id": session_id,
        "status": session.status.value,
        "plan": [s.model_dump(mode="json") for s in session.plan],
    }


@router.patch("/{session_id}/plan", summary="Update plan steps")
async def update_plan(session_id: str, request: UpdatePlanRequest) -> Dict[str, Any]:
    repo = _get_session_repo()
    session = await repo.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    if session.status == SessionStatus.EXECUTING:
        raise HTTPException(status_code=409, detail="Cannot update plan while executing")

    await repo.update_plan(session_id, request.steps)

    publish_to_session(session_id, {
        "type": "plan.updated",
        "session_id": session_id,
        "steps": [s.model_dump(mode="json") for s in request.steps],
        "at": datetime.now(timezone.utc).isoformat(),
    })

    return {"session_id": session_id, "status": "updated", "step_count": len(request.steps)}


@router.post("/{session_id}/plan/approve", summary="Lock plan and return input form metadata")
async def approve_plan(
    session_id: str,
    request: ApprovePlanRequest,
) -> Dict[str, Any]:
    """
    ADR-006: Locks the plan and returns the input form type + prefilled values.
    Does NOT start execution — the client must call /run after the user confirms inputs.
    """
    repo = _get_session_repo()
    session = await repo.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    if session.status == SessionStatus.EXECUTING:
        raise HTTPException(status_code=409, detail="Already executing")

    if not session.plan:
        raise HTTPException(status_code=422, detail="No plan to approve")

    await repo.set_status(session_id, SessionStatus.READY_TO_EXECUTE)

    # ADR-006: determine input form type from first enabled step's execution mode
    first_step = next((s for s in session.plan if s.enabled), None)
    input_form_type = "freetext"
    input_contract: Dict[str, Any] = {}
    prefilled_inputs: Dict[str, Any] = {}

    if first_step:
        cache = get_manifest_cache()
        cap = await cache.get_capability(first_step.capability_id)
        if cap:
            mode = (cap.get("execution") or {}).get("mode")
            if mode == "mcp":
                input_form_type = "structured"
                prefilled_inputs = first_step.run_inputs  # ADR-009: LLM-prefilled values
                # Discover input schema live from the MCP server's tools/list
                exec_cfg = cap.get("execution") or {}
                tool_name = exec_cfg.get("tool_name") or ""
                t = (exec_cfg.get("transport") or {})
                transport_cfg = MCPTransportConfig(
                    kind=(t.get("kind") or "http"),
                    base_url=t.get("base_url"),
                    headers=(t.get("headers") or {}),
                    protocol_path=(t.get("protocol_path") or "/mcp"),
                    verify_tls=t.get("verify_tls"),
                    timeout_sec=(t.get("timeout_sec") or 30),
                )
                try:
                    conn = await MCPConnection.connect(transport_cfg)
                    try:
                        pairs = await conn.list_tools()
                        tools = {name: schema for name, schema in pairs}
                        logger.info("[approve_plan] tools/list ok cap=%s tools=%s", first_step.capability_id, list(tools.keys()))
                        # Pick the target tool (named or first available)
                        target = tool_name if (tool_name and tool_name in tools) else (next(iter(tools), None))
                        raw_schema = tools.get(target) if target else None
                        # Grab description from tool object while connection still open
                        tool_obj = conn._tools.get(target) if target else None
                        schema_guide = (getattr(tool_obj, "description", None) or "") if tool_obj else ""
                    finally:
                        await conn.aclose()
                    if raw_schema:
                        input_contract = {"json_schema": raw_schema, "schema_guide": schema_guide}
                        logger.info("[approve_plan] input_contract built cap=%s props=%s", first_step.capability_id, list((raw_schema.get("properties") or {}).keys()))
                except Exception as exc:
                    logger.warning("[approve_plan] tools/list failed cap=%s err=%s — falling back to prefill schema", first_step.capability_id, exc, exc_info=True)

                # Fallback: derive schema from prefilled_inputs when MCP is unreachable
                if not input_contract and prefilled_inputs:
                    props = {}
                    for k, v in prefilled_inputs.items():
                        if isinstance(v, bool):
                            props[k] = {"type": "boolean", "title": k.replace("_", " ").title()}
                        else:
                            props[k] = {"type": "string", "title": k.replace("_", " ").title()}
                    input_contract = {
                        "json_schema": {"type": "object", "properties": props, "required": list(prefilled_inputs.keys())},
                        "schema_guide": "",
                    }
                    logger.info("[approve_plan] fallback schema from prefill cap=%s keys=%s", first_step.capability_id, list(props.keys()))

    publish_to_session(session_id, {
        "type": "plan.approved",
        "session_id": session_id,
        "input_form_type": input_form_type,
        "at": datetime.now(timezone.utc).isoformat(),
    })

    return {
        "session_id": session_id,
        "status": SessionStatus.READY_TO_EXECUTE.value,
        "input_form_type": input_form_type,
        "prefilled_inputs": prefilled_inputs,
        "input_contract": input_contract,
    }


@router.post("/{session_id}/run", summary="Submit user inputs and start execution")
async def run_plan(
    session_id: str,
    request: RunRequest,
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    """
    ADR-006: Accepts user-confirmed inputs and triggers execution.
    Must be called after /plan/approve.
    """
    repo = _get_session_repo()
    session = await repo.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    if session.status == SessionStatus.EXECUTING:
        raise HTTPException(status_code=409, detail="Already executing")

    if session.status != SessionStatus.READY_TO_EXECUTE:
        raise HTTPException(
            status_code=409,
            detail=f"Session must be in ready_to_execute state before running (current={session.status.value}). Call /plan/approve first.",
        )

    await repo.set_status(session_id, SessionStatus.EXECUTING)

    publish_to_session(session_id, {
        "type": "execution.started",
        "session_id": session_id,
        "at": datetime.now(timezone.utc).isoformat(),
    })

    background_tasks.add_task(_run_execution_bg, session_id, request)

    return {"session_id": session_id, "status": SessionStatus.EXECUTING.value}


@router.get("/{session_id}/runs/{run_id}", summary="Get execution run status")
async def get_run_status(session_id: str, run_id: str) -> Dict[str, Any]:
    run_repo = _get_run_repo()
    run = await run_repo.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return run


# ── Background tasks ─────────────────────────────────────────────────────────

async def _run_planner_bg(session_id: str, message: str) -> None:
    session_repo = _get_session_repo()
    run_repo = _get_run_repo()

    # Ensure a planner_runs document exists for this session (created on first message)
    try:
        session = await session_repo.get(session_id)
        if session and not session.active_run_id:
            run_id = await run_repo.create_planning_run(
                session_id=session_id,
                workspace_id=str(session.workspace_id) if session.workspace_id else "",
            )
            await session_repo.set_active_run(session_id, run_id)
        # Append the user message to planner_runs conversation
        await run_repo.append_conversation_message(
            session_id,
            {"role": "user", "content": message, "at": datetime.now(timezone.utc).isoformat()},
        )
    except Exception:
        logger.warning("Failed to init/update planner_runs for session=%s", session_id, exc_info=True)

    try:
        response = await invoke_planner(session_id=session_id, user_message=message)
        plan_steps = response.get("draft_plan", [])
        status = response.get("status", "planning")
        response_message = response.get("response_message", "")
        at = datetime.now(timezone.utc).isoformat()

        # Append assistant response to planner_runs conversation
        try:
            await run_repo.append_conversation_message(
                session_id,
                {"role": "assistant", "content": response_message, "at": at},
            )
        except Exception:
            logger.warning("Failed to append assistant message to planner_runs session=%s", session_id, exc_info=True)

        # planner.response is session-scoped — direct WS only, not RabbitMQ broadcast
        publish_to_session(session_id, {
            "type": "planner.response",
            "session_id": session_id,
            "message": response_message,
            "plan": plan_steps,
            "status": status,
            "at": at,
        })

    except Exception:
        logger.exception("Planner agent failed for session=%s", session_id)
        at = datetime.now(timezone.utc).isoformat()
        # planner.error is session-scoped — direct WS only, not RabbitMQ broadcast
        publish_to_session(session_id, {
            "type": "planner.error",
            "session_id": session_id,
            "error": "Planner agent encountered an error",
            "at": at,
        })


async def _run_execution_bg(session_id: str, run_request: RunRequest) -> None:
    session_repo = _get_session_repo()
    run_repo = _get_run_repo()
    try:
        session = await session_repo.get(session_id)
        workspace_id = run_request.workspace_id or (session.workspace_id if session else "")

        run_id = await run_execution_plan(
            session_id=session_id,
            strategy=run_request.strategy,
            workspace_id=workspace_id,
            run_inputs=run_request.run_inputs,
            session_repo=session_repo,
            run_repo=run_repo,
        )
        await session_repo.set_status(session_id, SessionStatus.COMPLETED)
        await session_repo.set_active_run(session_id, run_id)
        at = datetime.now(timezone.utc).isoformat()
        publish_to_session(session_id, {
            "type": "execution.completed",
            "session_id": session_id,
            "run_id": run_id,
            "at": at,
        })
        try:
            bus = get_bus()
            await bus.publish(
                service=Service.PLANNER.value,
                event="execution.completed",
                payload={
                    "type": "execution.completed",
                    "session_id": session_id,
                    "run_id": run_id,
                    "at": at,
                },
            )
        except Exception:
            logger.warning("RabbitMQ publish failed for execution.completed session=%s", session_id, exc_info=True)
    except Exception as e:
        logger.exception("Execution failed for session=%s", session_id)
        await session_repo.set_status(session_id, SessionStatus.FAILED)
        at = datetime.now(timezone.utc).isoformat()
        publish_to_session(session_id, {
            "type": "execution.failed",
            "session_id": session_id,
            "error": str(e),
            "at": at,
        })
        try:
            bus = get_bus()
            await bus.publish(
                service=Service.PLANNER.value,
                event="execution.failed",
                payload={
                    "type": "execution.failed",
                    "session_id": session_id,
                    "error": str(e),
                    "at": at,
                },
            )
        except Exception:
            logger.warning("RabbitMQ publish failed for execution.failed session=%s", session_id, exc_info=True)
