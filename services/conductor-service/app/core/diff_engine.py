# services/conductor-service/app/core/diff_engine.py
from __future__ import annotations

import copy
from typing import Any, Dict, List, Tuple

from app.clients.artifact_service import ArtifactServiceClient
from app.models.run_models import ArtifactEnvelope, ArtifactsDiffBuckets, RunDeltas


_IGNORE_FIELDS = {"artifact_id", "version", "fingerprint", "diagram_fingerprint", "narrative_fingerprint", "sha", "id", "ids"}


def _strip(d: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in d.items() if k not in _IGNORE_FIELDS}


async def compute_diffs(
    *,
    workspace_id: str,
    run_artifacts: List[ArtifactEnvelope],
    is_baseline: bool,
) -> Tuple[Dict[str, ArtifactsDiffBuckets], RunDeltas]:
    """
    Very lightweight diff:
      - fetch baseline parent
      - group by kind + natural identity (best-effort: identity dict as a key)
    """
    svc = ArtifactServiceClient()
    baseline_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
    try:
        parent = await svc.get_workspace_parent(workspace_id)
        for it in parent.get("artifacts", []):
            key = (it.get("kind"), str(_strip(it.get("data", {}))))
            baseline_map[key] = it
    except Exception:
        baseline_map = {}

    buckets_by_kind: Dict[str, ArtifactsDiffBuckets] = {}
    counts = {"new": 0, "updated": 0, "unchanged": 0, "retired": 0}

    for a in run_artifacts:
        key = (a.kind_id, str(_strip(a.data)))
        bkt = buckets_by_kind.setdefault(a.kind_id, ArtifactsDiffBuckets())
        if is_baseline:
            bkt.added.append(a)
            counts["new"] += 1
            continue

        if key in baseline_map:
            # unchanged
            bkt.unchanged.append(a)
            counts["unchanged"] += 1
        else:
            # changed or new — we don't have natural key comparison, so classify as updated/new based on identity name
            if a.identity and any(
                ((a.kind_id, str(_strip(it.get("data", {})))) in baseline_map) for it in baseline_map.values()
            ):
                bkt.changed.append(
                    # minimal before/after snapshot
                    {"kind_id": a.kind_id, "identity": a.identity, "before": {}, "after": a.data}  # type: ignore
                )
                counts["updated"] += 1
            else:
                bkt.added.append(a)
                counts["new"] += 1

    return buckets_by_kind, RunDeltas(counts=counts)