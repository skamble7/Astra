from __future__ import annotations

import logging
from typing import Any, Dict, Set

from app.clients.artifact_service import ArtifactServiceClient

logger = logging.getLogger("app.agent.nodes.kinds")


async def prefetch_kinds_and_index(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Collect produces_kinds from all capabilities in the selected playbook and fetch their registry entries.
    Defensive against missing/ill-formed playbooks.
    """
    pack = state.get("pack") or {}
    playbook = pack.get("playbook") or {}
    cap_by_id = pack.get("capabilities_by_id") or {}

    if not isinstance(playbook, dict):
        logger.warning("Playbook in state.pack.playbook is not a dict; skipping kind prefetch.")
        state.setdefault("registry", {}).setdefault("kinds_by_id", {})
        return state

    art = ArtifactServiceClient()

    kinds: Set[str] = set()
    for step in (playbook.get("steps") or []):
        if not isinstance(step, dict):
            continue
        cap_id = step.get("capability_id")
        if not cap_id:
            continue
        cap = cap_by_id.get(cap_id) or {}
        for k in (cap.get("produces_kinds") or []):
            if isinstance(k, str):
                kinds.add(k)

    kinds_by_id: Dict[str, Any] = {}
    for k in kinds:
        try:
            kinds_by_id[k] = await art.registry_get_kind(k)
        except Exception as e:
            logger.warning("Failed to fetch registry kind %s: %s", k, e)

    state.setdefault("registry", {})["kinds_by_id"] = kinds_by_id
    logger.info("Prefetched %d kinds", len(kinds_by_id))
    return state