from __future__ import annotations

import logging
import hashlib
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.db.run_repository import RunRepository
from app.models.run_models import (
    ArtifactEnvelope,
    ArtifactProvenance,
    RunStatus,
    RunDeltas,
)

logger = logging.getLogger("app.agent.nodes.persist_run")


def _sha256(obj: Any) -> str:
    try:
        import json
        s = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except Exception:
        s = repr(obj)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _derive_identity(
    *,
    raw: Dict[str, Any],
    kind_id: str,
    kind_specs: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Build an identity dict for an artifact:
    1) use provided 'identity' if present
    2) else use 'key' if present
    3) else map from kind.identity.natural_key fields in data
    4) else fall back to a content hash
    """
    if "identity" in raw and isinstance(raw["identity"], dict):
        return dict(raw["identity"])

    if "key" in raw and isinstance(raw["key"], str):
        return {"key": raw["key"]}

    data = raw.get("data") or {}
    natural = None
    try:
        natural = (kind_specs.get(kind_id) or {}).get("identity", {}).get("natural_key")
    except Exception:
        natural = None

    if natural and isinstance(natural, list):
        ident: Dict[str, Any] = {}
        for field in natural:
            if field in data:
                ident[field] = data[field]
        if ident:
            return ident

    # last resort
    return {"_hash": _sha256(data)}


def _choose_schema_version(kind_id: str, kind_specs: Dict[str, Any], raw: Dict[str, Any]) -> str:
    # prefer explicit schema_version in raw, else use latest from kind specs, else "1.0.0"
    if isinstance(raw.get("schema_version"), str) and raw["schema_version"]:
        return raw["schema_version"]
    try:
        return (kind_specs.get(kind_id) or {}).get("latest_schema_version") or "1.0.0"
    except Exception:
        return "1.0.0"


def _normalize_to_envelope(
    *,
    run_id: UUID,
    inputs_hash: Optional[str],
    raw: Dict[str, Any],
    kind_specs: Dict[str, Any],
) -> Optional[ArtifactEnvelope]:
    """
    Accept either an ArtifactEnvelope-shaped dict or raw MCP artifact:
    - Raw form is typically: { kind, key?, data, diagrams?, narratives?, provenance? }
    - We synthesize provenance if absent.
    """
    # Already a valid envelope?
    try:
        return ArtifactEnvelope.model_validate(raw)
    except Exception:
        pass  # try to normalize below

    # Try to normalize raw MCP artifact
    kind_id = raw.get("kind_id") or raw.get("kind")
    data = raw.get("data")
    if not isinstance(kind_id, str) or not isinstance(data, dict):
        # Not convertible
        return None

    schema_version = _choose_schema_version(kind_id, kind_specs, raw)
    identity = _derive_identity(raw=raw, kind_id=kind_id, kind_specs=kind_specs)

    prov_raw = raw.get("provenance") or {}
    step_id = prov_raw.get("step_id") or raw.get("step_id") or "unknown"
    capability_id = prov_raw.get("capability_id") or raw.get("capability_id") or "unknown"
    mode = prov_raw.get("mode") or raw.get("mode") or "mcp"  # default to MCP
    provenance = ArtifactProvenance(
        run_id=run_id,
        step_id=str(step_id),
        capability_id=str(capability_id),
        mode=str(mode),  # Literal enforced by model; mismatches will raise later
        inputs_hash=inputs_hash,
    )

    diagrams = raw.get("diagrams") or []
    narratives = raw.get("narratives") or []

    try:
        env = ArtifactEnvelope(
            kind_id=kind_id,
            schema_version=schema_version,
            identity=identity,
            data=data,
            diagrams=diagrams,
            narratives=narratives,
            provenance=provenance,
        )
        return env
    except Exception as e:
        logger.warning("[persist_run] Could not normalize artifact (kind=%s): %s", kind_id, str(e))
        return None


def persist_run_node(*, runs_repo: RunRepository):
    """
    Final node: persist staged_artifacts into pack_runs.run_artifacts, seal run status/summary.
    Idempotent: replaces run_artifacts with the produced set; safe to re-run.
    """

    async def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        run_doc: Dict[str, Any] = state["run"]
        run_id = UUID(run_doc["run_id"])
        staged: List[Dict[str, Any]] = state.get("staged_artifacts") or []
        logs: List[str] = state.get("logs", [])
        validations = state.get("validations", [])
        started_at_iso = state.get("started_at")
        completed_at_iso = state.get("completed_at") or datetime.now(timezone.utc).isoformat()
        last_mcp_error = state.get("last_mcp_error")
        inputs_hash: Optional[str] = state.get("input_fingerprint")
        kind_specs: Dict[str, Any] = state.get("artifact_kinds") or {}

        # Normalize artifacts (now accepts raw MCP items)
        envelopes: List[ArtifactEnvelope] = []
        dropped = 0
        for idx, raw in enumerate(staged):
            env = _normalize_to_envelope(
                run_id=run_id,
                inputs_hash=inputs_hash,
                raw=raw,
                kind_specs=kind_specs,
            )
            if env is not None:
                envelopes.append(env)
            else:
                dropped += 1
                logger.debug("[persist_run] Dropped non-convertible artifact idx=%d keys=%s", idx, list(raw.keys()))

        # Quick rollup metrics
        by_kind = Counter([e.kind_id for e in envelopes])
        persisted_count = len(envelopes)
        summary_msg = f"persist_run: persisted={persisted_count} kinds={dict(by_kind)}"
        if dropped:
            summary_msg += f" dropped={dropped}"
        if last_mcp_error:
            summary_msg += f" (last_mcp_error={last_mcp_error[:200]})"
        logs.append(summary_msg)

        # Decide final status
        final_status = RunStatus.FAILED if last_mcp_error else RunStatus.COMPLETED

        # Prepare run_summary updates
        run_summary_updates = {
            "validations": validations,
            "logs": logs,
            "started_at": started_at_iso,
            "completed_at": completed_at_iso,
        }

        # Persist atomically
        try:
            await runs_repo.finalize_run(
                run_id,
                run_artifacts=envelopes,
                status=final_status,
                diffs_by_kind=None,   # optional: left for a future diffing step
                deltas=None,          # optional
                run_summary_updates=run_summary_updates,
            )
        except Exception:
            logger.exception("[persist_run] finalize_run failed")
            # Best-effort: mark failed if finalize threw
            try:
                await runs_repo.finalize_run(
                    run_id,
                    run_artifacts=[],
                    status=RunStatus.FAILED,
                    diffs_by_kind=None,
                    deltas=None,
                    run_summary_updates={**run_summary_updates, "logs": logs + ["persist_run finalize failed"]},
                )
            except Exception:
                logger.exception("[persist_run] secondary finalize_run attempt also failed")

        # Return terminal update; graph END will apply
        return {
            "persist_summary": {
                "persisted_count": persisted_count,
                "kinds": dict(by_kind),
                "status": final_status.value,
                "dropped": dropped,
            },
            "staged_artifacts": [],  # optional cleanup in state
            "logs": logs,
            "completed_at": completed_at_iso,
        }

    return _node