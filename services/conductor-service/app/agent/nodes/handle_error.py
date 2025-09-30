# services/conductor-service/app/agent/nodes/handle_error.py
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID

from app.db.mongodb import get_client
from app.db.run_repository import RunRepository
from app.events.rabbit import get_bus

logger = logging.getLogger("app.agent.nodes.error")


async def handle_error(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transition run to failed and publish 'failed'.
    """
    err = state.get("error") or "unknown error"
    run_id = state["run"].get("run_id")
    if not run_id:
        # nothing persisted yet
        return state

    repo = RunRepository(get_client(), db_name=get_client().get_default_database().name)
    await repo.mark_failed(UUID(run_id), error=err)

    bus = get_bus()
    await bus.publish(
        service="conductor",
        event="failed",
        payload={
            "run_id": run_id,
            "workspace_id": state["run"]["workspace_id"],
            "error": err,
            "logs": state["aggregates"].get("logs") or [],
            "errors": [err],
            "artifact_failures": state["persistence"].get("artifact_failures") or [],
            "started_at": state["run"].get("started_at"),
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "title": state["run"]["title"],
            "description": state["run"]["description"],
            "strategy": state["run"]["strategy"],
        },
    )
    logger.error("Run failed: %s :: %s", run_id, err)
    return state