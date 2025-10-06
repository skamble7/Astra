# services/conductor-service/app/agent/nodes/persist_run.py
from __future__ import annotations

import logging
import hashlib
import base64
import os
from collections import Counter, defaultdict
from datetime import datetime, date, timezone
from typing import Any, Dict, List, Optional, Iterable, Tuple
from uuid import UUID

from app.db.run_repository import RunRepository
from app.models.run_models import (
    ArtifactEnvelope,
    ArtifactProvenance,
    RunStatus,
    RunStrategy,
)
from app.clients.artifact_service import ArtifactServiceClient

logger = logging.getLogger("app.agent.nodes.persist_run")


# ─────────────────────────────────────────────────────────────
# JSON helpers (sanitization + hashing)
# ─────────────────────────────────────────────────────────────
def _json_sanitize(x: Any) -> Any:
    if x is None or isinstance(x, (bool, int, float, str)):
        return x
    if isinstance(x, (datetime, date)):
        return x.isoformat()
    if isinstance(x, UUID):
        return str(x)
    if isinstance(x, bytes):
        return base64.b64encode(x).decode("ascii")
    if isinstance(x, (list, tuple, set)):
        return [_json_sanitize(v) for v in x]
    if isinstance(x, dict):
        return {str(k): _json_sanitize(v) for k, v in x.items()}
    if hasattr(x, "model_dump"):
        try:
            return _json_sanitize(x.model_dump())
        except Exception:
            pass
    if hasattr(x, "__dict__"):
        try:
            return _json_sanitize(vars(x))
        except Exception:
            pass
    return str(x)


def _sha256(obj: Any) -> str:
    try:
        import json
        s = json.dumps(_json_sanitize(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except Exception:
        s = repr(obj)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# ─────────────────────────────────────────────────────────────
# Identity / version helpers (local normalization only)
# ─────────────────────────────────────────────────────────────
def _derive_identity(*, raw: Dict[str, Any], kind_id: str, kind_specs: Dict[str, Any]) -> Dict[str, Any]:
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

    return {"_hash": _sha256(data)}


def _choose_schema_version(kind_id: str, kind_specs: Dict[str, Any], raw: Dict[str, Any]) -> str:
    if isinstance(raw.get("schema_version"), str) and raw["schema_version"]:
        return raw["schema_version"]
    try:
        return (kind_specs.get(kind_id) or {}).get("latest_schema_version") or "1.0.0"
    except Exception:
        return "1.0.0"


# ─────────────────────────────────────────────────────────────
# Name derivation (mirrors learning-service semantics)
# ─────────────────────────────────────────────────────────────
def _stable_hash(payload: Any, n: int = 10) -> str:
    try:
        import json
        s = json.dumps(_json_sanitize(payload), sort_keys=True, ensure_ascii=False, default=str)
    except Exception:
        s = repr(payload)
    import hashlib as _hl
    return _hl.sha1(s.encode("utf-8")).hexdigest()[:n]


def _derive_name(kind: str, data: Dict[str, Any]) -> str:
    kind = kind or ""
    data = data or {}

    if kind == "cam.asset.repo_snapshot":
        repo = (data.get("repo") or "").rstrip("/")
        base = os.path.basename(repo) or repo or "repo"
        commit = (data.get("commit") or "")[:12]
        return f"{base}@{commit}" if commit else base

    if kind == "cam.asset.source_index":
        root = (data.get("root") or "").rstrip("/")
        base = os.path.basename(root) or root or "source"
        return f"source-index:{base}"

    if kind == "cam.cobol.program":
        pid = data.get("program_id")
        if pid:
            return pid
        rel = (data.get("source") or {}).get("relpath")
        if rel:
            return os.path.splitext(os.path.basename(rel))[0] or rel
        return f"program:{_stable_hash(data)}"

    if kind == "cam.cobol.copybook":
        return data.get("name") or (data.get("source") or {}).get("relpath") or "copybook"

    return data.get("name") or (data.get("source") or {}).get("relpath") or kind or "artifact"


# ─────────────────────────────────────────────────────────────
# Envelope normalization
# ─────────────────────────────────────────────────────────────
def _normalize_to_envelope(
    *,
    run_id: UUID,
    inputs_hash: Optional[str],
    raw: Dict[str, Any],
    kind_specs: Dict[str, Any],
) -> Optional[ArtifactEnvelope]:
    try:
        return ArtifactEnvelope.model_validate(raw)
    except Exception:
        pass

    kind_id = raw.get("kind_id") or raw.get("kind")
    data = raw.get("data")
    if not isinstance(kind_id, str) or not isinstance(data, dict):
        return None

    schema_version = _choose_schema_version(kind_id, kind_specs, raw)
    identity = _derive_identity(raw=raw, kind_id=kind_id, kind_specs=kind_specs)

    prov_raw = raw.get("provenance") or {}
    step_id = prov_raw.get("step_id") or raw.get("step_id") or "unknown"
    capability_id = prov_raw.get("capability_id") or raw.get("capability_id") or "unknown"
    mode = prov_raw.get("mode") or raw.get("mode") or "mcp"
    provenance = ArtifactProvenance(
        run_id=run_id,
        step_id=str(step_id),
        capability_id=str(capability_id),
        mode=str(mode),
        inputs_hash=inputs_hash,
    )

    diagrams = raw.get("diagrams") or []
    narratives = raw.get("narratives") or []

    try:
        data_san = _json_sanitize(data)
        diagrams_san = _json_sanitize(diagrams)
        narratives_san = _json_sanitize(narratives)

        env = ArtifactEnvelope(
            kind_id=kind_id,
            schema_version=schema_version,
            identity=identity,
            data=data_san,
            diagrams=diagrams_san,
            narratives=narratives_san,
            provenance=provenance,
        )
        setattr(env, "_derived_name", _derive_name(kind_id, data_san))
        return env
    except Exception as e:
        logger.warning("[persist_run] Could not normalize artifact (kind=%s): %s", kind_id, str(e))
        return None


def _chunked(seq: List[Any], size: int) -> Iterable[List[Any]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


# ─────────────────────────────────────────────────────────────
# Mapping helpers for upsert-batch
# ─────────────────────────────────────────────────────────────
def _to_provenance(env: ArtifactEnvelope, *, pack_id: str, playbook_id: str) -> Dict[str, Any]:
    return {
        "run_id": str(env.provenance.run_id),
        "playbook_id": playbook_id or None,
        "step": env.provenance.step_id,
        "pack_key": pack_id or None,
        "inputs_fingerprint": env.provenance.inputs_hash,
    }


def _filter_diagrams(diagrams: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    out: List[Dict[str, Any]] = []
    for d in diagrams or []:
        instr = (d or {}).get("instructions")
        if not isinstance(instr, str) or not instr.strip():
            continue
        item = {
            "recipe_id": d.get("recipe_id"),
            "view": d.get("view"),
            "language": d.get("language") or "mermaid",
            "instructions": instr,
            "renderer_hints": d.get("renderer_hints"),
            "generated_from_fingerprint": d.get("generated_from_fingerprint"),
            "prompt_rev": d.get("prompt_rev"),
            "provenance": d.get("provenance"),
        }
        out.append(_json_sanitize(item))
    return out or None


def _filter_narratives(narrs: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    out: List[Dict[str, Any]] = []
    for n in narrs or []:
        body = (n or {}).get("body")
        if not isinstance(body, str) or not body.strip():
            continue
        item = {
            "id": n.get("id"),
            "title": n.get("title"),
            "format": n.get("format") or "markdown",
            "locale": n.get("locale") or "en-US",
            "audience": n.get("audience"),
            "tone": n.get("tone"),
            "body": body,
            "renderer_hints": n.get("renderer_hints"),
            "generated_from_fingerprint": n.get("generated_from_fingerprint"),
            "prompt_rev": n.get("prompt_rev"),
            "provenance": n.get("provenance"),
        }
        out.append(_json_sanitize(item))
    return out or None


# ─────────────────────────────────────────────────────────────
# Registry adaptation layer (strict to schema)
# ─────────────────────────────────────────────────────────────
def _adapt_for_registry(kind: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Coerce/strip fields to satisfy registry schema.

    - cam.asset.source_index:
        • drop nullable string fields (language_hint, encoding, program_id_guess) when None
    - cam.cobol.copybook:
        • rename `children` → `items` recursively
        • drop `occurs` if not a valid integer (coerce digit-strings)
        • drop `picture` when empty/whitespace
    """
    if not isinstance(data, dict):
        return data

    if kind == "cam.asset.source_index":
        files = data.get("files")
        if isinstance(files, list):
            cleaned: List[Dict[str, Any]] = []
            for f in files:
                if not isinstance(f, dict):
                    cleaned.append(f)
                    continue
                g = dict(f)
                for k in ("language_hint", "encoding", "program_id_guess"):
                    if k in g and g[k] is None:
                        del g[k]
                cleaned.append(g)
            return {**data, "files": cleaned}
        return data

    if kind == "cam.cobol.copybook":
        def fix_item(it: Any) -> Any:
            if not isinstance(it, dict):
                return it
            j = dict(it)

            # occurs: keep int; coerce digit-strings; else drop
            if "occurs" in j:
                val = j.get("occurs")
                if isinstance(val, int):
                    pass
                elif isinstance(val, str) and val.isdigit():
                    j["occurs"] = int(val)
                else:
                    j.pop("occurs", None)

            # picture: drop empty strings or whitespace
            if "picture" in j and isinstance(j["picture"], str) and not j["picture"].strip():
                j.pop("picture", None)

            # children -> items (recursive)
            if "children" in j:
                ch = j.get("children")
                if isinstance(ch, list):
                    j["items"] = [fix_item(c) for c in ch if isinstance(c, dict)]
                j.pop("children", None)

            # recurse into existing items
            if isinstance(j.get("items"), list):
                j["items"] = [fix_item(c) for c in j["items"]]

            return j

        items = data.get("items")
        if isinstance(items, list):
            return {**data, "items": [fix_item(i) for i in items]}
        return data

    return data


def _to_artifact_service_item(env: ArtifactEnvelope, *, pack_id: str, playbook_id: str) -> Dict[str, Any]:
    # Prefer derived semantic name (avoids NK collisions when registry has no identity rule)
    name = getattr(env, "_derived_name", None) or _derive_name(env.kind_id, env.data)

    # Sanitize and then adapt to registry schema
    sanitized_data = _json_sanitize(env.data)
    adapted_data = _adapt_for_registry(env.kind_id, sanitized_data if isinstance(sanitized_data, dict) else sanitized_data)

    item: Dict[str, Any] = {
        "kind": env.kind_id,
        "name": name,
        "data": adapted_data,
        "provenance": _to_provenance(env, pack_id=pack_id, playbook_id=playbook_id),
    }

    diagrams = _filter_diagrams(env.diagrams or [])
    if diagrams:
        item["diagrams"] = diagrams

    narratives = _filter_narratives(env.narratives or [])
    if narratives:
        item["narratives"] = narratives

    return item


def _dup_name_diagnostics(items: List[Dict[str, Any]]) -> Tuple[int, int, List[Tuple[str, List[int]]]]:
    groups: Dict[str, List[int]] = defaultdict(list)
    for idx, it in enumerate(items):
        groups[(it.get("kind") or "") + "|" + (it.get("name") or "")].append(idx)
    dup_examples: List[Tuple[str, List[int]]] = []
    for key, idxs in groups.items():
        if len(idxs) > 1 and len(dup_examples) < 5:
            dup_examples.append((key, idxs[:5]))
    return len(items), len(groups), dup_examples


# ─────────────────────────────────────────────────────────────
# Node
# ─────────────────────────────────────────────────────────────
async def _filter_known_kinds(client: ArtifactServiceClient, kinds: List[str], correlation_id: Optional[str]) -> set[str]:
    """
    Keep only kinds that exist in the registry. This mirrors learning-service's
    validate-before-persist behavior and prevents mass failures in upsert-batch.
    """
    known: set[str] = set()
    for k in sorted(set([x for x in kinds if x])):
        try:
            _ = await client.get_kind(k, correlation_id=correlation_id)
            known.add(k)
        except Exception:
            logger.warning("[persist_run] skipping unknown kind '%s' (not in registry)", k)
    return known


def persist_run_node(*, runs_repo: RunRepository, art_client: ArtifactServiceClient):
    async def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        run_doc: Dict[str, Any] = state["run"]
        run_id = UUID(run_doc["run_id"])
        workspace_id = run_doc["workspace_id"]
        pack_id = run_doc.get("pack_id") or ""
        playbook_id = run_doc.get("playbook_id") or ""
        strategy = (run_doc.get("strategy") or RunStrategy.DELTA).lower()

        staged: List[Dict[str, Any]] = state.get("staged_artifacts") or []
        logs: List[str] = state.get("logs", [])
        validations = state.get("validations", [])
        started_at_iso = state.get("started_at")
        completed_at_iso = state.get("completed_at") or datetime.now(timezone.utc).isoformat()
        last_mcp_error = state.get("last_mcp_error")
        inputs_hash: Optional[str] = state.get("input_fingerprint")
        kind_specs: Dict[str, Any] = state.get("artifact_kinds") or {}
        correlation_id: Optional[str] = state.get("correlation_id")

        # Normalize
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

        by_kind = Counter([e.kind_id for e in envelopes])

        # Filter to kinds that exist in registry to avoid mass batch failures
        kinds_needed = sorted(by_kind.keys())
        known_kinds: set[str] = set()
        try:
            # Reuse the provided client (do NOT construct with unsupported kwargs)
            known_kinds = await _filter_known_kinds(art_client, kinds_needed, correlation_id)
        except Exception:
            # Non-fatal: if the check fails, proceed (server will still validate)
            logger.warning("[persist_run] kind existence check failed; proceeding without filtering")

        if known_kinds:
            before = len(envelopes)
            envelopes = [e for e in envelopes if e.kind_id in known_kinds]
            if len(envelopes) != before:
                logs.append(f"persist_run: filtered_unknown_kinds removed={before-len(envelopes)} known={sorted(list(known_kinds))}")

        persisted_count = len(envelopes)
        summary_msg = f"persist_run: normalized={persisted_count} kinds={dict(Counter([e.kind_id for e in envelopes]))}"
        if dropped:
            summary_msg += f" dropped={dropped}"
        if last_mcp_error:
            summary_msg += f" (last_mcp_error={str(last_mcp_error)[:200]})"
        logs.append(summary_msg)

        # Final status for run doc
        final_status = RunStatus.FAILED if last_mcp_error else RunStatus.COMPLETED

        # Persist run snapshot
        run_summary_updates = {
            "validations": validations,
            "logs": logs,
            "started_at": started_at_iso,
            "completed_at": completed_at_iso,
        }
        try:
            await runs_repo.finalize_run(
                run_id,
                run_artifacts=envelopes,
                status=final_status,
                diffs_by_kind=None,
                deltas=None,
                run_summary_updates=run_summary_updates,
            )
        except Exception:
            logger.exception("[persist_run] finalize_run failed")
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

        # Promote baseline → artifact-service
        baseline_promoted = {"attempted": 0, "insert": 0, "update": 0, "noop": 0, "failed": 0, "chunks": 0, "errors": []}
        if strategy == RunStrategy.BASELINE.value and envelopes:
            items = [_to_artifact_service_item(e, pack_id=pack_id, playbook_id=playbook_id) for e in envelopes]
            baseline_promoted["attempted"] = len(items)

            # Log a tiny sanitized sample of the adapted payload to catch schema issues early
            try:
                sample = items[0] if items else None
                if sample:
                    sample_preview = {
                        "kind": sample.get("kind"),
                        "name": sample.get("name"),
                        "data_keys": sorted(list((sample.get("data") or {}).keys())),
                    }
                    logger.info("[persist_run] adapted_item_sample %s", sample_preview)
            except Exception:
                pass

            total, unique, dup_examples = _dup_name_diagnostics(items)
            logger.info(
                "[persist_run] baseline batch diagnostics: total=%d unique_kind_name=%d dup_groups=%d examples=%s",
                total, unique, len(dup_examples),
                "; ".join([f"{k} -> idxs={v}" for (k, v) in dup_examples]) if dup_examples else "none",
            )

            for chunk in _chunked(items, 200):
                try:
                    resp = await art_client.upsert_batch(
                        workspace_id=workspace_id,
                        items=chunk,
                        run_id=str(run_id),
                    )
                    if isinstance(resp, dict):
                        counts = resp.get("counts") or {}
                        for k in ("insert", "update", "noop", "failed"):
                            try:
                                baseline_promoted[k] += int(counts.get(k, 0))
                            except Exception:
                                pass

                        results = resp.get("results") or []
                        # Log a compact sample including error, if any
                        sample = results[: min(10, len(results))]
                        logger.info(
                            "[persist_run] batch_sample: %s",
                            [
                                {
                                    "kind": r.get("kind"),
                                    "name": r.get("name"),
                                    "nk": r.get("natural_key"),
                                    "op": r.get("op"),
                                    "ver": r.get("version"),
                                    "err": (r.get("error") or None),
                                }
                                for r in sample
                            ],
                        )
                        # Keep first few error messages for run logs
                        errs = [r for r in results if r.get("error")]
                        for e in errs[:3]:
                            msg = str(e.get("error") or "")[:300]
                            baseline_promoted["errors"].append(msg)
                    else:
                        baseline_promoted["insert"] += len(chunk)

                    baseline_promoted["chunks"] += 1
                except Exception as e:
                    msg = f"baseline upsert-batch failed: {e}"
                    logger.warning("[persist_run] %s", msg)
                    baseline_promoted["errors"].append(msg)

            logs.append(
                "baseline promotion: "
                f"attempted={baseline_promoted['attempted']} "
                f"insert={baseline_promoted['insert']} update={baseline_promoted['update']} "
                f"noop={baseline_promoted['noop']} failed={baseline_promoted['failed']} "
                f"chunks={baseline_promoted['chunks']} errors={len(baseline_promoted['errors'])}"
            )

        return {
            "persist_summary": {
                "persisted_count": len(envelopes),
                "kinds": dict(Counter([e.kind_id for e in envelopes])),
                "status": final_status.value,
                "dropped": dropped,
                "baseline_promoted": baseline_promoted if strategy == "baseline" else None,
            },
            "staged_artifacts": [],
            "logs": logs,
            "completed_at": completed_at_iso,
        }

    return _node