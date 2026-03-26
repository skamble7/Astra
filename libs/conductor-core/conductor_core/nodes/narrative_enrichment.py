# conductor_core/nodes/narrative_enrichment.py
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from uuid import UUID

from typing_extensions import Literal
from langgraph.types import Command

from conductor_core.protocols.repositories import RunRepositoryProtocol as RunRepository
from conductor_core.llm.base import AgentLLM
from conductor_core.models.run_models import StepAudit, ToolCallAudit

logger = logging.getLogger("conductor_core.nodes.narrative_enrichment")

_DATA_CLIP = 12_000   # chars of artifact JSON sent to LLM
_PROMPT_SAMPLE = 800  # chars logged for debugging


def _artifact_kind_id(a: Dict[str, Any]) -> Optional[str]:
    for key in ("kind_id", "kind", "_kind", "artifact_kind", "type"):
        v = a.get(key)
        if isinstance(v, str) and v:
            return v
    return None


def _artifact_data(a: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    data = a.get("data")
    if isinstance(data, dict):
        return data
    wrapped_keys = {"kind", "kind_id", "schema_version", "identity", "diagrams", "narratives", "provenance"}
    if isinstance(a, dict) and not (wrapped_keys & set(a.keys())):
        return a
    return None


def _latest_schema_entry(kind_spec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(kind_spec, dict):
        return None
    latest = kind_spec.get("latest_schema_version")
    versions = kind_spec.get("schema_versions") or []
    if isinstance(latest, str):
        for sv in versions:
            if isinstance(sv, dict) and sv.get("version") == latest:
                return sv
    return versions[0] if versions and isinstance(versions[0], dict) else None


def _select_artifacts_for_step(*, staged: List[Dict[str, Any]], step_id: Optional[str]) -> List[Dict[str, Any]]:
    """
    STRICT SCOPING: Only return artifacts produced in the current step.
    Never fall back to all staged artifacts; that would cause cross-step leakage.
    """
    if not staged or not step_id:
        return []
    return [a for a in staged if isinstance(a, dict) and a.get("produced_in_step_id") == step_id]


def _json_sample(val: Any, limit: int = 1000) -> str:
    try:
        s = val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)
    except Exception:
        s = "<unserializable>"
    return s[:limit] + ("…" if len(s) > limit else "")


def _build_narrative_prompt(
    *,
    kind_id: str,
    kind_title: Optional[str],
    kind_system_prompt: Optional[str],
    data_obj: Dict[str, Any],
    default_format: str,
    max_length_chars: int,
    locale: str,
) -> str:
    data_str = json.dumps(data_obj, ensure_ascii=False, indent=2)
    if len(data_str) > _DATA_CLIP:
        data_str = data_str[:_DATA_CLIP] + "\n… (truncated)"

    lines: List[str] = [
        "You are generating a human-readable narrative explanation for a structured software artifact.",
        "",
    ]

    if kind_system_prompt:
        lines += [
            "=== ARTIFACT KIND CONTEXT ===",
            kind_system_prompt.strip(),
            "",
        ]
    elif kind_title:
        lines += [
            f"=== ARTIFACT KIND ===",
            f"ID: {kind_id}",
            f"Title: {kind_title}",
            "",
        ]
    else:
        lines += [
            f"=== ARTIFACT KIND ===",
            f"ID: {kind_id}",
            "",
        ]

    lines += [
        "=== ARTIFACT DATA ===",
        data_str,
        "",
        "=== NARRATIVE REQUIREMENTS ===",
        f"- Format: {default_format}",
        f"- Maximum length: {max_length_chars} characters",
        f"- Locale: {locale}",
        "- Audience: technical developer",
        "- Tone: explanatory",
        "",
        f"Write a clear {default_format} narrative that explains this artifact to a technical audience.",
        "Cover what it represents, its key components, and its significance within the broader system.",
        "Do not wrap your response in JSON, code fences, or any other container.",
        "Output only the narrative text.",
    ]

    return "\n".join(lines)


def narrative_enrichment_node(*, runs_repo: RunRepository, llm: AgentLLM):
    async def _node(state: Dict[str, Any]) -> Command[Literal["capability_executor"]] | Dict[str, Any]:
        run = state["run"]
        run_uuid = UUID(run["run_id"])
        current_step_id = state.get("current_step_id")

        artifact_kinds: Dict[str, Any] = state.get("artifact_kinds") or {}
        staged: List[Dict[str, Any]] = state.get("staged_artifacts") or []

        artifacts = _select_artifacts_for_step(staged=staged, step_id=current_step_id)
        if not artifacts:
            note = "No staged artifacts for current step; narrative enrichment skipped."
            logger.info("[narrative] skip reason=no_artifacts_for_step step_id=%s", current_step_id)
            return Command(
                goto="capability_executor",
                update={
                    "last_narrative_summary": {
                        "completed_step_id": current_step_id,
                        "artifacts_considered": 0,
                        "narratives_written": 0,
                        "narratives_failed": 0,
                        "narratives_skipped": 0,
                        "missing_kind_specs": [],
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "note": note,
                    },
                    "last_narrative_error": None,
                },
            )

        written = 0
        failed = 0
        skipped = 0
        missing_kinds: Set[str] = set()
        step_audit_calls: List[ToolCallAudit] = []

        updated_staged = list(staged)

        try:
            for idx, art in enumerate(artifacts):
                kind_id = _artifact_kind_id(art)
                kind_spec = artifact_kinds.get(kind_id) if kind_id else None
                if kind_id and not kind_spec:
                    missing_kinds.add(kind_id)

                schema_entry = _latest_schema_entry(kind_spec) if kind_spec else None
                narratives_spec = (schema_entry or {}).get("narratives_spec") if schema_entry else None

                if not narratives_spec:
                    skipped += 1
                    logger.info(
                        "[narrative] skip idx=%d reason=no_narratives_spec kind=%s",
                        idx, kind_id,
                    )
                    continue

                data_obj = _artifact_data(art)
                if not isinstance(data_obj, dict):
                    failed += 1
                    logger.info("[narrative] skip idx=%d reason=no_data kind=%s", idx, kind_id)
                    continue

                # Extract narratives_spec fields
                default_format = (narratives_spec.get("default_format") or "markdown")
                max_length_chars = int(narratives_spec.get("max_length_chars") or 20000)
                allowed_locales = narratives_spec.get("allowed_locales") or ["en-US"]
                locale = allowed_locales[0] if allowed_locales else "en-US"

                # Kind context for prompt
                kind_title = (kind_spec or {}).get("title")
                kind_system_prompt = (schema_entry or {}).get("prompt", {}).get("system") if schema_entry else None
                prompt_rev = (schema_entry or {}).get("prompt", {}).get("version") if schema_entry else None

                prompt = _build_narrative_prompt(
                    kind_id=kind_id or "<unknown>",
                    kind_title=kind_title,
                    kind_system_prompt=kind_system_prompt,
                    data_obj=data_obj,
                    default_format=default_format,
                    max_length_chars=max_length_chars,
                    locale=locale,
                )

                logger.info(
                    "[narrative] call idx=%d kind=%s format=%s max_chars=%d",
                    idx, kind_id, default_format, max_length_chars,
                )
                logger.debug("[narrative] prompt_sample idx=%d %s", idx, _json_sample(prompt, _PROMPT_SAMPLE))

                call_started = datetime.now(timezone.utc)
                call_status: Literal["ok", "failed"] = "ok"
                narrative_body = ""
                validation_errors: List[str] = []

                try:
                    result = await llm.acomplete(prompt)
                    narrative_body = (result.text or "").strip()
                    # Respect max_length_chars constraint
                    if len(narrative_body) > max_length_chars:
                        narrative_body = narrative_body[:max_length_chars]
                    logger.info(
                        "[narrative] result idx=%d kind=%s body_len=%d",
                        idx, kind_id, len(narrative_body),
                    )
                except Exception as llm_err:
                    call_status = "failed"
                    msg = f"{type(llm_err).__name__}: {llm_err}"
                    validation_errors = [msg]
                    logger.error("[narrative] llm_error idx=%d kind=%s msg=%s", idx, kind_id, msg)

                duration_ms = int((datetime.now(timezone.utc) - call_started).total_seconds() * 1000)
                call_audit = ToolCallAudit(
                    user_prompt=prompt[:_PROMPT_SAMPLE],
                    raw_output_sample=_json_sample(narrative_body, 800),
                    validation_errors=validation_errors,
                    duration_ms=duration_ms,
                    status=call_status,
                )
                step_audit_calls.append(call_audit)
                await runs_repo.append_tool_call_audit(run_uuid, current_step_id or "<unknown-step>", call_audit)

                if call_status == "failed" or not narrative_body:
                    failed += 1
                    continue

                # Attach narrative to the artifact
                narrative_item = {
                    "id": "auto:overview",
                    "title": "Overview",
                    "format": default_format,
                    "locale": locale,
                    "body": narrative_body,
                    "provenance": {
                        "capability_id": "narrative_enrichment",
                        "mode": "llm",
                        "ts": datetime.now(timezone.utc).isoformat(),
                    },
                    "prompt_rev": prompt_rev,
                }

                try:
                    original_idx = updated_staged.index(art)
                    new_art = dict(updated_staged[original_idx])
                    existing_narratives = new_art.get("narratives") if isinstance(new_art.get("narratives"), list) else []
                    new_art["narratives"] = existing_narratives + [narrative_item]
                    updated_staged[original_idx] = new_art
                except ValueError:
                    na = dict(art)
                    na["narratives"] = [narrative_item]
                    updated_staged.append(na)

                written += 1
                logger.info(
                    "[narrative] narrative_attached idx=%d kind=%s body_len=%d",
                    idx, kind_id, len(narrative_body),
                )

        except Exception as e:
            err_msg = f"narrative_enrichment execution error: {e}"
            logger.error("[narrative] error step_id=%s msg=%s", current_step_id, err_msg)
            return Command(
                goto="capability_executor",
                update={
                    "last_narrative_summary": {
                        "completed_step_id": current_step_id,
                        "artifacts_considered": len(artifacts),
                        "narratives_written": written,
                        "narratives_failed": failed + (len(artifacts) - written - failed - skipped),
                        "narratives_skipped": skipped,
                        "missing_kind_specs": sorted(list(missing_kinds)) if missing_kinds else [],
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "note": "unexpected exception; narrative enrichment partially completed",
                    },
                    "last_narrative_error": err_msg,
                },
            )

        # Final audit
        await runs_repo.append_step_audit(
            run_uuid,
            StepAudit(
                step_id=current_step_id or "<unknown-step>",
                capability_id="narrative_enrichment",
                mode="llm",
                inputs_preview={
                    "phase": "narrative-enrichment",
                    "artifacts_considered": len(artifacts),
                },
                calls=step_audit_calls,
            ),
        )

        logger.info(
            "[narrative] handoff step_id=%s artifacts=%d written=%d failed=%d skipped=%d missing_kinds=%d",
            current_step_id, len(artifacts), written, failed, skipped, len(missing_kinds),
        )

        return Command(
            goto="capability_executor",
            update={
                "staged_artifacts": updated_staged,
                "last_narrative_summary": {
                    "completed_step_id": current_step_id,
                    "artifacts_considered": len(artifacts),
                    "narratives_written": written,
                    "narratives_failed": failed,
                    "narratives_skipped": skipped,
                    "missing_kind_specs": sorted(list(missing_kinds)) if missing_kinds else [],
                    "ts": datetime.now(timezone.utc).isoformat(),
                },
                "last_narrative_error": None if failed == 0 else "Some narratives failed to generate",
            },
        )

    return _node
