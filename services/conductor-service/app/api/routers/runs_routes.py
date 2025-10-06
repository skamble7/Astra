# services/conductor-service/app/api/routers/runs_routes.py
from __future__ import annotations

import logging
import time
from typing import Any, Dict
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request

from app.config import settings
from app.db.mongodb import get_client
from app.db.run_repository import RunRepository
from app.models.run_models import (
    PlaybookRun,
    RunStatus,
    StartRunRequest,
    RunStrategy,
    RunSummary,
)
from app.clients.capability_service import CapabilityServiceClient
from app.clients.artifact_service import ArtifactServiceClient
from app.agent.graph import run_input_bootstrap

router = APIRouter(prefix="/runs", tags=["runs"])
logger = logging.getLogger("app.api.runs")


def _repo() -> RunRepository:
    return RunRepository(get_client(), settings.mongo_db)


async def _execute_run(run: PlaybookRun, start_request: Dict[str, Any]) -> None:
    """
    Background task: perform the full run lifecycle (mark started -> execute graph -> persist summary).
    Any exceptions are handled here and reflected into run status; they do NOT affect the API caller.
    """
    runs_repo = _repo()
    cap_client = CapabilityServiceClient()
    art_client = ArtifactServiceClient()

    # Mark started (server-side timestamp)
    try:
        await runs_repo.mark_started(run.run_id)
    except Exception:
        logger.exception("[run %s] mark_started failed", run.run_id)
        # Keep going; run may still be recoverable

    t0 = time.perf_counter()
    try:
        final_state = await run_input_bootstrap(
            runs_repo=runs_repo,
            cap_client=cap_client,
            art_client=art_client,
            start_request=start_request,
            run_doc=run,
        )
        # Courtesy timing fields (persist_run already set completed_at/status)
        duration_s = round(time.perf_counter() - t0, 3)
        try:
            await runs_repo.update_run_summary(
                run.run_id,
                validations=final_state.get("validations", []),
                started_at=run.created_at,
                completed_at=datetime.now(timezone.utc),
                duration_s=duration_s,
            )
        except Exception:
            logger.warning("[run %s] Non-fatal: update_run_summary post-run failed", run.run_id, exc_info=True)
    except Exception as e:
        logger.exception("[run %s] Run bootstrap failed", run.run_id)
        try:
            await runs_repo.mark_failed(run.run_id, error=f"Bootstrap failed: {e}")
        except Exception:
            logger.warning("[run %s] mark_failed also failed", run.run_id, exc_info=True)


@router.post("/start", status_code=202)
async def start_run(payload: StartRunRequest, request: Request, background: BackgroundTasks) -> Dict[str, Any]:
    """
    Fire-and-forget start:
      - Create the run record
      - Queue execution as a background task
      - Return immediately with 202 and basic run info
    """
    runs_repo = _repo()

    run = PlaybookRun(
        workspace_id=payload.workspace_id,
        pack_id=payload.pack_id,
        playbook_id=payload.playbook_id,
        title=payload.title,
        description=payload.description,
        strategy=payload.strategy or RunStrategy.DELTA,
        status=RunStatus.CREATED,  # will transition to STARTED in background
        inputs=payload.inputs or {},
        run_summary=RunSummary(
            validations=[],
            logs=[],
            started_at=datetime.now(timezone.utc),
        ),
    )

    # Persist initial run doc
    await runs_repo.create(run)

    # Launch execution in background (non-blocking for the caller)
    background.add_task(_execute_run, run, payload.model_dump(mode="json"))

    # Respond immediately
    return {
        "run_id": str(run.run_id),
        "status": RunStatus.CREATED.value,  # effectively "queued"
        "pack_id": run.pack_id,
        "playbook_id": run.playbook_id,
        "strategy": run.strategy.value if hasattr(run.strategy, "value") else str(run.strategy),
        "message": "Run accepted and scheduled.",
    }