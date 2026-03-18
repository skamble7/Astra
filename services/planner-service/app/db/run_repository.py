# services/planner-service/app/db/run_repository.py
"""
RunRepository for planner-service's execution agent.
Implements RunRepositoryProtocol from conductor_core.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import ASCENDING, ReturnDocument

from conductor_core.models.run_models import (
    PlaybookRun, RunStatus, StepStatus, StepState, ToolCallAudit, StepAudit,
    ArtifactEnvelope, RunDeltas,
)
from app.db.mongodb import get_db

logger = logging.getLogger("app.db.runs")

COLLECTION_NAME = "planner_runs"


class RunRepository:
    def __init__(self) -> None:
        self._col: AsyncIOMotorCollection = get_db()[COLLECTION_NAME]

    async def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        doc = await self._col.find_one({"run_id": run_id})
        if doc:
            doc.pop("_id", None)
        return doc

    async def create_planning_run(self, session_id: str, workspace_id: str) -> str:
        """Create a lightweight planner_runs document at the start of a planning session."""
        run_id = str(uuid4())
        now = datetime.now(timezone.utc)
        doc = {
            "run_id": run_id,
            "session_id": session_id,
            "workspace_id": workspace_id,
            "status": "planning",
            "conversation": [],
            "steps": [],
            "run_artifacts": [],
            "created_at": now,
            "updated_at": now,
        }
        await self._col.insert_one(doc)
        return run_id

    async def append_conversation_message(self, session_id: str, message: Dict[str, Any]) -> None:
        """Append a chat message to the conversation history in the planner_runs document."""
        await self._col.update_one(
            {"session_id": session_id},
            {
                "$push": {"conversation": message},
                "$set": {"updated_at": datetime.now(timezone.utc)},
            },
        )

    async def get_run_by_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Find the planner_runs document for a session (created during planning)."""
        doc = await self._col.find_one({"session_id": session_id})
        if doc:
            doc.pop("_id", None)
        return doc

    async def init_execution(
        self,
        session_id: str,
        *,
        steps: List[StepState],
        strategy: RunStrategy,
        workspace_id: str,
    ) -> str:
        """Transition an existing planning run document to execution state."""
        now = datetime.now(timezone.utc)
        await self._col.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "status": RunStatus.RUNNING.value,
                    "strategy": strategy.value,
                    "workspace_id": workspace_id,
                    "steps": [s.model_dump(mode="json") for s in steps],
                    "updated_at": now,
                }
            },
        )
        doc = await self._col.find_one({"session_id": session_id}, {"run_id": 1})
        return str(doc["run_id"]) if doc else ""

    async def create_run(self, run: PlaybookRun) -> PlaybookRun:
        doc = run.model_dump(mode="json")
        await self._col.insert_one(doc)
        return run

    async def step_started(self, run_id: UUID, step_id: str) -> None:
        await self._col.update_one(
            {"run_id": str(run_id), "steps.id": step_id},
            {"$set": {
                "steps.$.status": StepStatus.RUNNING.value,
                "steps.$.started_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }},
        )

    async def step_completed(self, run_id: UUID, step_id: str, *, metrics: Dict[str, Any]) -> None:
        await self._col.update_one(
            {"run_id": str(run_id), "steps.id": step_id},
            {"$set": {
                "steps.$.status": StepStatus.COMPLETED.value,
                "steps.$.completed_at": datetime.now(timezone.utc),
                "steps.$.metrics": metrics,
                "updated_at": datetime.now(timezone.utc),
            }},
        )

    async def step_failed(self, run_id: UUID, step_id: str, *, error: str) -> None:
        await self._col.update_one(
            {"run_id": str(run_id), "steps.id": step_id},
            {"$set": {
                "steps.$.status": StepStatus.FAILED.value,
                "steps.$.error": error,
                "steps.$.completed_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }},
        )

    async def step_skipped(self, run_id: UUID, step_id: str, *, reason: str) -> None:
        await self._col.update_one(
            {"run_id": str(run_id), "steps.id": step_id},
            {"$set": {
                "steps.$.status": StepStatus.SKIPPED.value,
                "steps.$.error": reason,
                "updated_at": datetime.now(timezone.utc),
            }},
        )

    async def init_steps(self, run_id: UUID, steps: List[StepState]) -> None:
        await self._col.update_one(
            {"run_id": str(run_id)},
            {"$set": {
                "steps": [s.model_dump(mode="json") for s in steps],
                "updated_at": datetime.now(timezone.utc),
            }},
        )

    async def append_tool_call_audit(self, run_id: UUID, step_id: str, audit: ToolCallAudit) -> None:
        await self._col.update_one(
            {"run_id": str(run_id)},
            {"$push": {f"step_audits.{step_id}.tool_calls": audit.model_dump(mode="json")}},
        )

    async def append_step_audit(self, run_id: UUID, audit: StepAudit) -> None:
        await self._col.update_one(
            {"run_id": str(run_id)},
            {"$push": {"step_audits_list": audit.model_dump(mode="json")}},
        )

    async def finalize_run(
        self,
        run_id: UUID,
        *,
        run_artifacts: List[ArtifactEnvelope],
        status: RunStatus,
        diffs_by_kind: Optional[Any],
        deltas: Optional[Any],
        run_summary_updates: Dict[str, Any],
    ) -> None:
        artifacts_json = [a.model_dump(mode="json") for a in run_artifacts]
        update: Dict[str, Any] = {
            "status": status.value,
            "run_artifacts": artifacts_json,
            "updated_at": datetime.now(timezone.utc),
            **run_summary_updates,
        }
        if diffs_by_kind is not None:
            update["diffs_by_kind"] = diffs_by_kind
        if deltas is not None:
            update["deltas"] = (deltas.model_dump(mode="json") if hasattr(deltas, "model_dump") else deltas)

        await self._col.update_one(
            {"run_id": str(run_id)},
            {"$set": update},
        )
