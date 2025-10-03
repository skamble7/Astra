# services/conductor-service/app/api/routers/runs_routes.py
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import ORJSONResponse

from app.agent.graph import spawn_agent_task
from app.config import settings
from app.db.mongodb import get_client
from app.db.run_repository import RunRepository
from app.models.run_models import StartRunRequest

router = APIRouter(prefix="/runs", tags=["runs"])
logger = logging.getLogger("app.api.runs")


@router.post(
    "/",
    response_class=ORJSONResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start a new run",
    response_description="Accepted; run starts asynchronously",
)
async def start_run(req: StartRunRequest) -> Dict[str, Any]:
    """
    Start a run. Validates request against `StartRunRequest` so
    `workspace_id` must be a UUID and `inputs` is an object.

    Returns 202 with a run_id (best-effort; may be null if ingestion hasn't stamped it yet).
    """
    # Prepare initial agent state (ingest node will persist the run and stamp run_id)
    state: Dict[str, Any] = {
        "request": req.model_dump(mode="json"),
        "run": {
            "run_id": None,  # set by ingest node after creating the document
            "workspace_id": str(req.workspace_id),
            "pack_id": req.pack_id,
            "playbook_id": req.playbook_id,
            "title": req.title,
            "description": req.description,
        },
    }

    # Fire-and-forget agent execution
    task = spawn_agent_task(state)
    logger.info("Spawned run task: %s", task.get_name())

    # Best-effort: briefly wait for ingest node to create run and stamp run_id
    run_id = None
    for _ in range(20):  # ~1s total (20 * 50ms)
        await asyncio.sleep(0.05)
        rid = state.get("run", {}).get("run_id")
        if rid:
            run_id = rid
            break

    return {"accepted": True, "run_id": run_id}


@router.get(
    "/{run_id}",
    response_class=ORJSONResponse,
    summary="Get run by id",
)
async def get_run(run_id: str) -> Dict[str, Any]:
    """
    Fetch a previously started run by UUID.
    """
    try:
        _ = UUID(run_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid run_id")

    client = get_client()
    repo = RunRepository(client, db_name=settings.mongo_db)
    run = await repo.get(UUID(run_id))
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    # Ensure UUIDs and other special types are JSON-safe
    return run.model_dump(mode="json", by_alias=True)