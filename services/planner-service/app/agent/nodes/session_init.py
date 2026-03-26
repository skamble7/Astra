# services/planner-service/app/agent/nodes/session_init.py
from __future__ import annotations

import logging
from typing import Any, Dict

from app.db.session_repository import SessionRepository

logger = logging.getLogger("app.agent.nodes.session_init")


def session_init_node(*, session_repo: SessionRepository):
    async def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        session_id = state.get("session_id")
        if not session_id:
            return {"error": "session_id missing", "status": "failed"}

        try:
            session = await session_repo.get(session_id)
            if not session:
                return {"error": f"Session '{session_id}' not found", "status": "failed"}

            return {
                "session_id": session.session_id,
                "org_id": session.org_id,
                "workspace_id": session.workspace_id,
                "messages": [m.model_dump(mode="json") for m in session.messages],
                "existing_plan": [s.model_dump(mode="json") for s in (session.plan or [])],
                "status": session.status.value,
            }
        except Exception as e:
            logger.exception("[session_init] error session=%s: %s", session_id, e)
            return {"error": str(e), "status": "failed"}

    return _node
