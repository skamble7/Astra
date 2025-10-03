# services/conductor-service/app/api/routers/runs_routes.py
from __future__ import annotations

import logging
import time
from typing import Any, Dict
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

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


@router.post("/start")
async def start_run(payload: StartRunRequest) -> Dict[str, Any]:
    """
    Create a run document, execute the input_resolver graph node,
    and return the initialized run + bootstrap state summary.
    """
    runs_repo = _repo()
    cap_client = CapabilityServiceClient()
    art_client = ArtifactServiceClient()

    # 1) Create run doc
    run = PlaybookRun(
        workspace_id=payload.workspace_id,
        pack_id=payload.pack_id,
        playbook_id=payload.playbook_id,
        title=payload.title,
        description=payload.description,
        strategy=payload.strategy or RunStrategy.DELTA,  # fixed: don't reference run before assignment
        status=RunStatus.CREATED,
        inputs=payload.inputs or {},
        # Seed a non-null run_summary so dotted-path updates never fail on null parent
        run_summary=RunSummary(
            validations=[],
            logs=[],
            started_at=datetime.now(timezone.utc),
        ),
    )
    await runs_repo.create(run)

    # 2) Mark started
    await runs_repo.mark_started(run.run_id)

    # 3) Invoke the single-node graph to bootstrap state
    t0 = time.perf_counter()
    try:
        final_state = await run_input_bootstrap(
            runs_repo=runs_repo,
            cap_client=cap_client,
            art_client=art_client,
            start_request=payload.model_dump(mode="json"),
            run_doc=run,
        )
    except Exception as e:
        logger.exception("Run bootstrap failed")
        await runs_repo.mark_failed(run.run_id, error=f"Bootstrap failed: {e}")
        raise HTTPException(status_code=500, detail=f"Bootstrap failed: {e}") from e

    # 4) Summarize & mark completed (this endpoint performs only bootstrap)
    duration_s = round(time.perf_counter() - t0, 3)
    await runs_repo.update_run_summary(
        run.run_id,
        validations=final_state.get("validations", []),
        started_at=run.created_at,
        completed_at=run.updated_at,
        duration_s=duration_s,
    )
    await runs_repo.mark_completed(
        run.run_id,
        run_summary={
            "validations": final_state.get("validations", []),
            "logs": final_state.get("logs", []),
            "started_at": final_state.get("started_at"),
            "completed_at": final_state.get("completed_at"),
            "duration_s": duration_s,
        },
    )

    # 5) API response
    return {
        "run_id": str(run.run_id),
        "status": RunStatus.COMPLETED.value,
        "pack_id": run.pack_id,
        "playbook_id": run.playbook_id,
        "steps": final_state.get("steps", []),
        "inputs_valid": final_state.get("inputs_valid", False),
        "input_errors": final_state.get("input_errors", []),
        "input_fingerprint": final_state.get("input_fingerprint"),
        "artifact_kinds_loaded": sorted(list(final_state.get("artifact_kinds", {}).keys())),
        "logs": final_state.get("logs", []),
        "validations": final_state.get("validations", []),
    }