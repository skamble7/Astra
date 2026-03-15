# services/planner-service/app/agent/nodes/clarification.py
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from app.db.session_repository import SessionRepository
from app.models.session_models import SessionStatus, ChatMessage, MessageRole

logger = logging.getLogger("app.agent.nodes.clarification")


def clarification_node(*, session_repo: SessionRepository):
    async def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        session_id = state.get("session_id", "")
        question = state.get("clarification_question") or "Could you provide more details about your request?"

        # Save clarification question as assistant message
        try:
            msg = ChatMessage(role=MessageRole.ASSISTANT, content=question)
            await session_repo.append_message(session_id, msg)
            await session_repo.set_status(session_id, SessionStatus.AWAITING_CLARIFICATION)
        except Exception as e:
            logger.warning("[clarification] failed to persist: %s", e)

        logger.info("[clarification] asking clarification session=%s", session_id)
        return {
            "response_message": question,
            "status": SessionStatus.AWAITING_CLARIFICATION.value,
        }

    return _node
