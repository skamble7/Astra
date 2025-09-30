# services/conductor-service/app/agent/nodes/persist_results.py
from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.clients.artifact_service import ArtifactServiceClient
from app.models.run_models import ArtifactEnvelope

logger = logging.getLogger("app.agent.nodes.persist")


async def persist_results(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Persist final artifacts:
      - Baseline: upsert artifacts into artifact-service (workspace baseline source of truth).
      - Delta: keep artifacts in conductor run doc only (already appended step-wise).
    Also publish the interim 'completed' (B) event in the publish_summary node next.
    """
    strategy = state["run"]["strategy"]
    artifacts: List[ArtifactEnvelope] = state["aggregates"]["run_artifacts"]
    if strategy == "baseline" and artifacts:
        svc = ArtifactServiceClient()
        items = []
        for a in artifacts:
            items.append({
                "kind": a.kind_id,
                "name": a.identity.get("name") or a.identity.get("id") or "unknown",
                "data": a.data,
                "diagrams": a.diagrams,
                "narratives": a.narratives,
                "natural_key": a.identity.get("name") or a.identity,  # allow string or object
                "provenance": {"run_id": state["run"]["run_id"], "playbook_id": state["run"]["playbook_id"]},
            })
        # chunk if large; here we do one batch
        await svc.upsert_batch(state["run"]["workspace_id"], items, run_id=state["run"]["run_id"])
        logger.info("Baseline artifacts upserted: %d", len(items))
    return state