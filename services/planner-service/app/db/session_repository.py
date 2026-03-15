# services/planner-service/app/db/session_repository.py
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorCollection

from app.db.mongodb import get_db
from app.models.session_models import PlannerSession, SessionStatus, ChatMessage, PlanStep

logger = logging.getLogger("app.db.sessions")

COLLECTION_NAME = "planner_sessions"


class SessionRepository:
    def __init__(self) -> None:
        self._col: AsyncIOMotorCollection = get_db()[COLLECTION_NAME]

    async def create(self, session: PlannerSession) -> PlannerSession:
        doc = session.model_dump_mongo()
        await self._col.insert_one(doc)
        return session

    async def get(self, session_id: str) -> Optional[PlannerSession]:
        doc = await self._col.find_one({"session_id": session_id})
        if not doc:
            return None
        doc.pop("_id", None)
        return PlannerSession.model_validate(doc)

    async def get_or_raise(self, session_id: str) -> PlannerSession:
        session = await self.get(session_id)
        if session is None:
            raise ValueError(f"Session '{session_id}' not found")
        return session

    async def set_status(self, session_id: str, status: SessionStatus) -> None:
        await self._col.update_one(
            {"session_id": session_id},
            {"$set": {"status": status.value, "updated_at": datetime.now(timezone.utc)}},
        )

    async def append_message(self, session_id: str, message: ChatMessage) -> None:
        await self._col.update_one(
            {"session_id": session_id},
            {
                "$push": {"messages": message.model_dump(mode="json")},
                "$set": {"updated_at": datetime.now(timezone.utc)},
            },
        )

    async def update_plan(self, session_id: str, steps: List[PlanStep]) -> None:
        steps_json = [s.model_dump(mode="json") for s in steps]
        await self._col.update_one(
            {"session_id": session_id},
            {"$set": {"plan": steps_json, "updated_at": datetime.now(timezone.utc)}},
        )

    async def update_intent(self, session_id: str, intent: Dict[str, Any]) -> None:
        await self._col.update_one(
            {"session_id": session_id},
            {"$set": {"intent": intent, "updated_at": datetime.now(timezone.utc)}},
        )

    async def set_active_run(self, session_id: str, run_id: str) -> None:
        await self._col.update_one(
            {"session_id": session_id},
            {"$set": {"active_run_id": run_id, "updated_at": datetime.now(timezone.utc)}},
        )

    async def list_by_org(self, org_id: str, limit: int = 50) -> List[PlannerSession]:
        cursor = self._col.find({"org_id": org_id}).sort("created_at", -1).limit(limit)
        results = []
        async for doc in cursor:
            doc.pop("_id", None)
            try:
                results.append(PlannerSession.model_validate(doc))
            except Exception:
                pass
        return results
