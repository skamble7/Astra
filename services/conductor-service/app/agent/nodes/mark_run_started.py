# services/conductor-service/app/agent/nodes/mark_run_started.py
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import UUID

from app.db.mongodb import get_client
from app.db.run_repository import RunRepository
from app.events.rabbit import get_bus
from app.models.run_models import StepState, StepStatus

logger = logging.getLogger("app.agent.nodes.run_started")


async def mark_run_started(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Persist initial step states, transition run to RUNNING, publish 'started'.
    """
    run_id = UUID(state["run"]["run_id"])
    client = get_client()
    repo = RunRepository(client, db_name=client.get_default_database().name)

    steps: List[StepState] = []
    for st in (state["pack"]["playbook"]["steps"] or []):
        steps.append(
            StepState(step_id=st["id"], capability_id=st["capability_id"], name=st.get("name"))
        )
    await repo.init_steps(run_id, steps)
    await repo.mark_started(run_id)

    now = datetime.now(timezone.utc).isoformat()
    state["run"]["started_at"] = now

    # event: started
    bus = get_bus()
    await bus.publish(
        service="conductor",
        event="started",
        payload={
            "run_id": state["run"]["run_id"],
            "workspace_id": state["run"]["workspace_id"],
            "playbook_id": state["run"]["playbook_id"],
            "model_id": state.get("llm", {}).get("model"),
            "received_at": now,
            "title": state["run"]["title"],
            "description": state["run"]["description"],
            "strategy": state["run"]["strategy"],
        },
    )

    logger.info("Run marked started: %s", state["run"]["run_id"])
    return state