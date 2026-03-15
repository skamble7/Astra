# services/planner-service/app/api/routers/session_routes.py
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, BackgroundTasks

from app.db.session_repository import SessionRepository
from app.db.run_repository import RunRepository
from app.models.session_models import (
    PlannerSession,
    CreateSessionRequest,
    SendMessageRequest,
    UpdatePlanRequest,
    ApprovePlanRequest,
    SessionStatus,
    ChatMessage,
    MessageRole,
)
from app.agent.planner_graph import invoke_planner
from app.agent.execution_graph import run_execution_plan
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

    # Publish plan update event to WebSocket stream
    publish_to_session(session_id, {
        "type": "plan.updated",
        "session_id": session_id,
        "steps": [s.model_dump(mode="json") for s in request.steps],
        "at": datetime.now(timezone.utc).isoformat(),
    })

    return {"session_id": session_id, "status": "updated", "step_count": len(request.steps)}


@router.post("/{session_id}/plan/approve", summary="Approve plan and trigger execution")
async def approve_plan(
    session_id: str,
    request: ApprovePlanRequest,
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    repo = _get_session_repo()
    session = await repo.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

    if session.status == SessionStatus.EXECUTING:
        raise HTTPException(status_code=409, detail="Already executing")

    if not session.plan:
        raise HTTPException(status_code=422, detail="No plan to approve")

    await repo.set_status(session_id, SessionStatus.EXECUTING)

    publish_to_session(session_id, {
        "type": "execution.started",
        "session_id": session_id,
        "at": datetime.now(timezone.utc).isoformat(),
    })

    background_tasks.add_task(
        _run_execution_bg,
        session_id,
        request.strategy,
        request.workspace_id or session.workspace_id,
    )

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
    try:
        response = await invoke_planner(session_id=session_id, user_message=message)
        # draft_plan is the correct state key — PlannerState uses "draft_plan", not "plan"
        plan_steps = response.get("draft_plan", [])
        status = response.get("status", "planning")
        response_message = response.get("response_message", "")
        at = datetime.now(timezone.utc).isoformat()

        # 1) Push to direct WebSocket subscribers (PlannerStream in extension)
        publish_to_session(session_id, {
            "type": "planner.response",
            "session_id": session_id,
            "message": response_message,
            "plan": plan_steps,
            "status": status,
            "at": at,
        })

        # 2) Publish to RabbitMQ so the notification service broadcasts to output window
        try:
            bus = get_bus()
            await bus.publish(
                service=Service.PLANNER.value,
                event="session.response",
                payload={
                    "type": "planner.response",
                    "session_id": session_id,
                    "message": response_message,
                    "plan": plan_steps,
                    "status": status,
                    "at": at,
                },
            )
        except Exception:
            logger.warning("RabbitMQ publish failed for planner.response session=%s", session_id, exc_info=True)

    except Exception:
        logger.exception("Planner agent failed for session=%s", session_id)
        at = datetime.now(timezone.utc).isoformat()
        publish_to_session(session_id, {
            "type": "planner.error",
            "session_id": session_id,
            "error": "Planner agent encountered an error",
            "at": at,
        })
        try:
            bus = get_bus()
            await bus.publish(
                service=Service.PLANNER.value,
                event="session.error",
                payload={
                    "type": "planner.error",
                    "session_id": session_id,
                    "error": "Planner agent encountered an error",
                    "at": at,
                },
            )
        except Exception:
            logger.warning("RabbitMQ publish failed for planner.error session=%s", session_id, exc_info=True)


async def _run_execution_bg(session_id: str, strategy: str, workspace_id: str) -> None:
    session_repo = _get_session_repo()
    run_repo = _get_run_repo()
    try:
        run_id = await run_execution_plan(
            session_id=session_id,
            strategy=strategy,
            workspace_id=workspace_id,
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
