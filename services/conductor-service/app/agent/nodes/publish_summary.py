# services/conductor-service/app/agent/nodes/publish_summary.py
from __future__ import annotations

import logging
from typing import Any, Dict

from app.events.rabbit import get_bus

logger = logging.getLogger("app.agent.nodes.publish_summary")


async def publish_summary(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Publish the interim 'completed' (B) event with deltas after persist.
    """
    bus = get_bus()
    deltas = state["aggregates"].get("deltas") or {"counts": {}}
    await bus.publish(
        service="conductor",
        event="completed",
        payload={
            "run_id": state["run"]["run_id"],
            "workspace_id": state["run"]["workspace_id"],
            "playbook_id": state["run"]["playbook_id"],
            "artifact_ids": [],                # optional: collect from artifact-service response if needed
            "artifact_failures": state["persistence"].get("artifact_failures") or [],
            "validations": [v for v in state["aggregates"].get("validations") or []],
            "deltas": deltas,
        },
    )
    logger.info("Interim completed (B) published")
    return state