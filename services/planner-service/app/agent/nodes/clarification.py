# services/planner-service/app/agent/nodes/clarification.py
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from app.db.session_repository import SessionRepository
from app.models.session_models import SessionStatus, ChatMessage, MessageRole, PlanStep

logger = logging.getLogger("app.agent.nodes.clarification")


def clarification_node(*, session_repo: SessionRepository):
    async def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        session_id = state.get("session_id", "")
        question = state.get("clarification_question") or "Could you provide more details about your request?"
        draft_plan = state.get("draft_plan") or []

        # Save clarification question as assistant message
        try:
            msg = ChatMessage(role=MessageRole.ASSISTANT, content=question)
            await session_repo.append_message(session_id, msg)
            await session_repo.set_status(session_id, SessionStatus.AWAITING_CLARIFICATION)
        except Exception as e:
            logger.warning("[clarification] failed to persist: %s", e)

        # Persist the draft plan even when clarification is needed — the user can
        # still see and approve it, and the /approve endpoint reads from session.plan.
        if draft_plan:
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
                    logger.warning("[clarification] invalid step: %s", e)
            try:
                await session_repo.update_plan(session_id, plan_steps)
            except Exception as e:
                logger.warning("[clarification] failed to persist draft plan: %s", e)

        logger.info("[clarification] asking clarification session=%s", session_id)
        return {
            "response_message": question,
            "status": SessionStatus.AWAITING_CLARIFICATION.value,
        }

    return _node
