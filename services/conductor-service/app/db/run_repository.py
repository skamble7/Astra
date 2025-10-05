# services/conductor-service/app/db/run_repository.py
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pymongo import ASCENDING, DESCENDING, ReturnDocument

from app.models.run_models import (
    PlaybookRun,
    RunStatus,
    StepStatus,
    StepState,
    ToolCallAudit,
    StepAudit,
    ArtifactEnvelope,
    RunDeltas,
)

logger = logging.getLogger("app.db.runs")

COLLECTION_NAME = "pack_runs"


class RunRepository:
    """
    DAL for the 'pack_runs' collection.
    - One document per run (run-owned artifacts for DELTA, audit trail, step state).
    - Baseline artifacts are managed by artifact-service and not duplicated here.
    """

    def __init__(self, client: AsyncIOMotorClient, db_name: str) -> None:
        self._db = client[db_name]
        self._col: AsyncIOMotorCollection = self._db[COLLECTION_NAME]

    # ---------- bootstrap ---------- #

    async def ensure_indexes(self) -> None:
        await self._col.create_index([("run_id", ASCENDING)], name="uk_run_id", unique=True)
        await self._col.create_index([("workspace_id", ASCENDING), ("created_at", DESCENDING)], name="ix_ws_created")
        await self._col.create_index([("status", ASCENDING), ("created_at", DESCENDING)], name="ix_status_created")
        await self._col.create_index([("pack_id", ASCENDING)], name="ix_pack_id")
        await self._col.create_index([("playbook_id", ASCENDING)], name="ix_playbook_id")

    # ---------- CRUD ---------- #

    async def create(self, run: PlaybookRun) -> PlaybookRun:
        # JSON mode converts UUIDs to strings and datetimes to ISO 8601
        doc = run.model_dump(by_alias=True, mode="json")
        await self._col.insert_one(doc)
        return run

    async def get(self, run_id: UUID) -> Optional[PlaybookRun]:
        doc = await self._col.find_one({"run_id": str(run_id)})
        return PlaybookRun.model_validate(doc) if doc else None

    async def list_by_workspace(
        self, workspace_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> List[PlaybookRun]:
        cursor = (
            self._col.find({"workspace_id": str(workspace_id)})
            .sort("created_at", DESCENDING)
            .skip(offset)
            .limit(limit)
        )
        return [PlaybookRun.model_validate(d) async for d in cursor]

    # ---------- lifecycle transitions ---------- #

    async def mark_started(self, run_id: UUID) -> Optional[PlaybookRun]:
        now = datetime.now(timezone.utc)
        doc = await self._col.find_one_and_update(
            {"run_id": str(run_id)},
            {"$set": {"status": RunStatus.RUNNING.value, "updated_at": now}},
            return_document=ReturnDocument.AFTER,
        )
        return PlaybookRun.model_validate(doc) if doc else None

    async def mark_completed(
        self,
        run_id: UUID,
        *,
        run_summary: Optional[Dict[str, Any]] = None,
    ) -> Optional[PlaybookRun]:
        now = datetime.now(timezone.utc)
        updates: Dict[str, Any] = {
            "status": RunStatus.COMPLETED.value,
            "updated_at": now,
        }
        if run_summary:
            updates["run_summary"] = run_summary
        doc = await self._col.find_one_and_update(
            {"run_id": str(run_id)},
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )
        return PlaybookRun.model_validate(doc) if doc else None

    async def mark_failed(self, run_id: UUID, *, error: str | None = None) -> Optional[PlaybookRun]:
        now = datetime.now(timezone.utc)
        set_ops: Dict[str, Any] = {"status": RunStatus.FAILED.value, "updated_at": now}
        if error:
            set_ops["notes_md"] = (error if len(error) < 4000 else error[:4000] + "…")
        doc = await self._col.find_one_and_update(
            {"run_id": str(run_id)},
            {"$set": set_ops},
            return_document=ReturnDocument.AFTER,
        )
        return PlaybookRun.model_validate(doc) if doc else None

    # ---------- step state ---------- #

    async def init_steps(self, run_id: UUID, steps: List[StepState]) -> None:
        await self._col.update_one(
            {"run_id": str(run_id)},
            {"$set": {"steps": [s.model_dump(mode="json") for s in steps], "updated_at": datetime.now(timezone.utc)}},
        )

    async def step_started(self, run_id: UUID, step_id: str) -> None:
        now = datetime.now(timezone.utc)
        await self._col.update_one(
            {"run_id": str(run_id), "steps.step_id": step_id},
            {
                "$set": {
                    "steps.$.status": StepStatus.RUNNING.value,
                    "steps.$.started_at": now,
                    "steps.$.error": None,
                    "updated_at": now,
                }
            },
        )

    async def step_completed(self, run_id: UUID, step_id: str, *, metrics: Optional[Dict[str, Any]] = None) -> None:
        now = datetime.now(timezone.utc)
        set_ops: Dict[str, Any] = {
            "steps.$.status": StepStatus.COMPLETED.value,
            "steps.$.completed_at": now,
            "updated_at": now,
        }
        if metrics:
            set_ops["steps.$.metrics"] = metrics
        await self._col.update_one(
            {"run_id": str(run_id), "steps.step_id": step_id},
            {"$set": set_ops},
        )

    async def step_failed(self, run_id: UUID, step_id: str, *, error: str) -> None:
        now = datetime.now(timezone.utc)
        await self._col.update_one(
            {"run_id": str(run_id), "steps.step_id": step_id},
            {
                "$set": {
                    "steps.$.status": StepStatus.FAILED.value,
                    "steps.$.completed_at": now,
                    "steps.$.error": error[:2000] if error else None,
                    "updated_at": now,
                }
            },
        )

    async def step_skipped(self, run_id: UUID, step_id: str, *, reason: Optional[str] = None) -> None:
        now = datetime.now(timezone.utc)
        await self._col.update_one(
            {"run_id": str(run_id), "steps.step_id": step_id},
            {
                "$set": {
                    "steps.$.status": StepStatus.SKIPPED.value,
                    "steps.$.completed_at": now,
                    "steps.$.error": (reason[:2000] if reason else None),
                    "updated_at": now,
                }
            },
        )

    # ---------- audit trail ---------- #

    async def append_step_audit(self, run_id: UUID, audit: StepAudit) -> None:
        await self._col.update_one(
            {"run_id": str(run_id)},
            {"$push": {"audit": audit.model_dump(mode="json")}, "$set": {"updated_at": datetime.now(timezone.utc)}},
        )

    async def append_tool_call_audit(self, run_id: UUID, step_id: str, call: ToolCallAudit) -> None:
        """
        Push a call audit into the last StepAudit with matching step_id.
        If not present, create a StepAudit envelope on the fly.
        """
        now = datetime.now(timezone.utc)
        payload = call.model_dump(mode="json")
        # try to push into existing StepAudit entry
        result = await self._col.update_one(
            {"run_id": str(run_id), "audit.step_id": step_id},
            {"$push": {"audit.$.calls": payload}, "$set": {"updated_at": now}},
        )
        if result.matched_count == 0:
            # create a new StepAudit envelope with this single call
            await self._col.update_one(
                {"run_id": str(run_id)},
                {
                    "$push": {
                        "audit": {
                            "step_id": step_id,
                            "capability_id": "",
                            "mode": "mcp",
                            "inputs_preview": {},
                            "calls": [payload],
                        }
                    },
                    "$set": {"updated_at": now},
                },
            )

    # ---------- artifacts & deltas (DELTA run-owned) ---------- #

    async def append_run_artifacts(self, run_id: UUID, items: List[ArtifactEnvelope]) -> None:
        """
        Store run-owned artifacts in the conductor document (DELTA runs).
        Keep this list modest; very large sets should be chunked by caller.
        """
        await self._col.update_one(
            {"run_id": str(run_id)},
            {
                "$push": {
                    "run_artifacts": {"$each": [i.model_dump(mode="json") for i in items]}
                },
                "$set": {"updated_at": datetime.now(timezone.utc)},
            },
        )

    async def set_diffs(self, run_id: UUID, *, diffs_by_kind: Dict[str, Any], deltas: Optional[RunDeltas]) -> None:
        await self._col.update_one(
            {"run_id": str(run_id)},
            {
                "$set": {
                    "diffs_by_kind": diffs_by_kind,
                    "deltas": deltas.model_dump(mode="json") if deltas else None,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )

    # ---------- finalize (idempotent replace) ---------- #

    async def finalize_run(
        self,
        run_id: UUID,
        *,
        run_artifacts: List[ArtifactEnvelope],
        status: RunStatus,
        diffs_by_kind: Optional[Dict[str, Any]] = None,
        deltas: Optional[RunDeltas] = None,
        run_summary_updates: Optional[Dict[str, Any]] = None,
    ) -> Optional[PlaybookRun]:
        """
        Single atomic write to seal a run:
        - Replace run_artifacts
        - Set status
        - Optionally set diffs/deltas
        - Merge run_summary updates (replace semantics per provided keys)
        Idempotent: re-running with same inputs leads to same stored arrays.
        """
        now = datetime.now(timezone.utc)

        set_ops: Dict[str, Any] = {
            "run_artifacts": [i.model_dump(mode="json") for i in run_artifacts],
            "status": status.value,
            "updated_at": now,
        }
        if diffs_by_kind is not None:
            set_ops["diffs_by_kind"] = diffs_by_kind
        if deltas is not None:
            set_ops["deltas"] = deltas.model_dump(mode="json")

        if run_summary_updates is not None:
            # Ensure run_summary exists before updating dotted fields
            await self._col.update_one(
                {"run_id": str(run_id), "run_summary": None},
                {"$set": {"run_summary": {}}},
            )
            for k, v in run_summary_updates.items():
                set_ops[f"run_summary.{k}"] = v

        doc = await self._col.find_one_and_update(
            {"run_id": str(run_id)},
            {"$set": set_ops},
            return_document=ReturnDocument.AFTER,
        )
        return PlaybookRun.model_validate(doc) if doc else None

    # ---------- free-form notes/logs ---------- #

    async def append_log(self, run_id: UUID, message: str) -> None:
        await self._col.update_one(
            {"run_id": str(run_id)},
            {"$push": {"run_summary.logs": message}, "$set": {"updated_at": datetime.now(timezone.utc)}},
        )

    # ---------- utility ---------- #

    async def update_run_summary(
        self,
        run_id: UUID,
        *,
        validations: Optional[List[Dict[str, Any]]] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        duration_s: Optional[float] = None,
    ) -> None:
        # Ensure run_summary is an object (not null) before setting dotted subfields
        await self._col.update_one(
            {"run_id": str(run_id), "run_summary": None},
            {"$set": {"run_summary": {}}},
        )

        set_ops: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
        if validations is not None:
            set_ops["run_summary.validations"] = validations
        if started_at is not None:
            set_ops["run_summary.started_at"] = started_at
        if completed_at is not None:
            set_ops["run_summary.completed_at"] = completed_at
        if duration_s is not None:
            set_ops["run_summary.duration_s"] = duration_s

        await self._col.update_one({"run_id": str(run_id)}, {"$set": set_ops})
    