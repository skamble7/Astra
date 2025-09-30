# services/conductor-service/app/agent/nodes/compute_diffs_vs_baseline.py
from __future__ import annotations

import logging
from typing import Any, Dict
from uuid import UUID

from app.db.mongodb import get_client
from app.db.run_repository import RunRepository
from app.core.diff_engine import compute_diffs

logger = logging.getLogger("app.agent.nodes.diffs")


async def compute_diffs_vs_baseline(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute diffs between produced artifacts (run-owned) and workspace baseline (from artifact-service).
    For a baseline run, everything is 'added'.
    """
    run_id = UUID(state["run"]["run_id"])
    client = get_client()
    repo = RunRepository(client, db_name=client.get_default_database().name)

    diffs_by_kind, deltas = await compute_diffs(
        workspace_id=state["run"]["workspace_id"],
        run_artifacts=state["aggregates"]["run_artifacts"],
        is_baseline=(state["run"]["strategy"] == "baseline"),
    )
    await repo.set_diffs(run_id, diffs_by_kind=diffs_by_kind, deltas=deltas)
    state["aggregates"]["deltas"] = deltas.model_dump() if deltas else None
    logger.info("Diffs computed")
    return state