# services/conductor-service/app/agent/nodes/prefetch_kinds_and_index.py
from __future__ import annotations

import logging
from typing import Any, Dict, Set

from app.clients.artifact_service import ArtifactServiceClient

logger = logging.getLogger("app.agent.nodes.kinds")


async def prefetch_kinds_and_index(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Collect produces_kinds from all capabilities in the selected playbook and fetch their registry entries.
    """
    playbook = state["pack"]["playbook"]
    cap_by_id = state["pack"]["capabilities_by_id"]
    art = ArtifactServiceClient()

    kinds: Set[str] = set()
    for step in (playbook.get("steps") or []):
        cap_id = step["capability_id"]
        cap = cap_by_id.get(cap_id) or {}
        for k in cap.get("produces_kinds", []) or []:
            kinds.add(k)

    kinds_by_id: Dict[str, Any] = {}
    for k in kinds:
        try:
            kinds_by_id[k] = await art.registry_get_kind(k)
        except Exception as e:
            logger.warning("Failed to fetch registry kind %s: %s", k, e)

    state["registry"]["kinds_by_id"] = kinds_by_id
    logger.info("Prefetched %d kinds", len(kinds_by_id))
    return state