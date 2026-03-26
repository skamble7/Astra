# services/planner-service/app/agent/nodes/plan_approved.py
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from app.db.session_repository import SessionRepository
from app.models.session_models import (
    SessionStatus, ChatMessage, MessageRole, PlanStep
)

logger = logging.getLogger("app.agent.nodes.plan_approved")


def plan_approved_node(*, session_repo: SessionRepository):
    async def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        session_id = state.get("session_id", "")
        draft_plan = state.get("draft_plan") or []
        confidence = state.get("confidence_score", 0.0)
        response_msg = state.get("response_message", "I've assembled a plan for you.")
        intent = state.get("intent") or {}

        # Convert draft plan to PlanStep objects
        plan_steps = []
        for s in draft_plan:
            try:
                plan_steps.append(PlanStep(
                    step_id=s.get("step_id", ""),
                    capability_id=s.get("capability_id", ""),
                    title=s.get("title", ""),
                    description=s.get("description"),
                    inputs=s.get("inputs") or {},
                    run_inputs=s.get("run_inputs") or {},
                    order=s.get("order", len(plan_steps) + 1),
                    enabled=s.get("enabled", True),
                ))
            except Exception as e:
                logger.warning("[plan_approved] invalid step: %s", e)

        try:
            await session_repo.update_plan(session_id, plan_steps)
            await session_repo.update_intent(session_id, intent)
            await session_repo.set_status(session_id, SessionStatus.READY_TO_EXECUTE)

            # Save assistant response as message
            msg = ChatMessage(role=MessageRole.ASSISTANT, content=response_msg)
            await session_repo.append_message(session_id, msg)
        except Exception as e:
            logger.warning("[plan_approved] persistence failed: %s", e)

        logger.info("[plan_approved] plan saved session=%s steps=%d", session_id, len(plan_steps))
        return {
            "plan": [s.model_dump(mode="json") for s in plan_steps],
            "status": SessionStatus.READY_TO_EXECUTE.value,
            "response_message": response_msg,
        }

    return _node
