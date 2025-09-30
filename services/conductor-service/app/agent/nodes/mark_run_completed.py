# services/conductor-service/app/agent/nodes/mark_run_completed.py
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID

from app.db.mongodb import get_client
from app.db.run_repository import RunRepository
from app.events.rabbit import get_bus

logger = logging.getLogger("app.agent.nodes.run_completed")


async def mark_run_completed(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mark run completed in DAL and publish final 'completed' (A).
    """
    client = get_client()
    repo = RunRepository(client, db_name=client.get_default_database().name)

    run_id = UUID(state["run"]["run_id"])
    started_at_iso = state["run"].get("started_at")
    completed_at = datetime.now(timezone.utc)
    duration_s = None
    if started_at_iso:
        try:
            from datetime import datetime as dt
            started_at = dt.fromisoformat(started_at_iso.replace("Z", "+00:00"))
            duration_s = (completed_at - started_at).total_seconds()
        except Exception:
            duration_s = None

    await repo.mark_completed(run_id, run_summary={
        "validations": state["aggregates"].get("validations") or [],
        "logs": state["aggregates"].get("logs") or [],
        "started_at": started_at_iso,
        "completed_at": completed_at,
        "duration_s": duration_s,
    })

    bus = get_bus()
    await bus.publish(
        service="conductor",
        event="completed",
        payload={
            "run_id": state["run"]["run_id"],
            "workspace_id": state["run"]["workspace_id"],
            "playbook_id": state["run"]["playbook_id"],
            "artifact_ids": [],
            "validations": [v for v in state["aggregates"].get("validations") or []],
            "logs": [l for l in state["aggregates"].get("logs") or []],
            "started_at": started_at_iso,
            "completed_at": completed_at.isoformat(),
            "duration_s": duration_s,
            "title": state["run"]["title"],
            "description": state["run"]["description"],
        },
    )

    state["run"]["completed_at"] = completed_at.isoformat()
    return state