# services/conductor-service/app/agent/nodes/llm_execution.py
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone
from uuid import UUID
import asyncio
import json
import logging

from typing_extensions import Literal
from jsonschema import Draft202012Validator, ValidationError
from langgraph.types import Command

from app.db.run_repository import RunRepository
from app.models.run_models import StepAudit, ToolCallAudit
from app.secrets.resolver import SecretResolver
from app.llm.execution_factory import build_exec_llm
from app.llm.execution_base import ExecLLM

logger = logging.getLogger("app.agent.nodes.llm_execution")


# ------------- helpers -------------
def _json_preview(obj: Any, limit: int = 600) -> str:
    try:
        s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    except Exception:
        s = "<unserializable>"
    return s[:limit] + ("…" if len(s) > limit else "")


def _latest_schema_entry(kind_spec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(kind_spec, dict):
        return None
    target_ver = kind_spec.get("latest_schema_version")
    versions = kind_spec.get("schema_versions") or []
    if not versions:
        return None
    if target_ver:
        for v in versions:
            if v.get("version") == target_ver:
                return v
    # fallback to first
    return versions[0]


def _collect_dependencies(staged: List[Dict[str, Any]], depends_on: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """
    From already-staged artifacts, gather those matching depends_on.hard/soft lists.
    Returns: { kind_id: [artifact.data, ...], ... }
    """
    want: List[str] = []
    if isinstance(depends_on, dict):
        for k in ("hard", "soft"):
            for kid in depends_on.get(k) or []:
                if isinstance(kid, str) and kid not in want:
                    want.append(kid)

    by_kind: Dict[str, List[Dict[str, Any]]] = {}
    if not want:
        return by_kind

    for raw in staged or []:
        kind = raw.get("kind_id") or raw.get("kind")
        if isinstance(kind, str) and kind in want:
            data = raw.get("data")
            if isinstance(data, dict):
                by_kind.setdefault(kind, []).append(data)
    return by_kind


def _mk_user_prompt(
    kind_id: str,
    schema_entry: Dict[str, Any],
    dep_payload: Dict[str, List[Dict[str, Any]]]
) -> Tuple[str, Dict[str, Any]]:
    """
    Builds a strict user prompt instructing the LLM to emit JSON only,
    consistent with the artifact kind's json_schema.
    Returns: (user_prompt_text, json_schema)
    """
    json_schema = (schema_entry.get("json_schema") or {})
    prompt_meta = (schema_entry.get("prompt") or {})
    strict_json = bool(prompt_meta.get("strict_json", False))

    # Summarize dependencies (compact to keep prompt size reasonable)
    deps_summary = {k: v[:10] for k, v in (dep_payload or {}).items()}

    # IMPORTANT: use f-strings only; DO NOT call .format() because braces in JSON will be treated as placeholders.
    usr = (
        f"You are generating an artifact instance for kind '{kind_id}'. "
        "Use the JSON Schema provided below. Output strictly one JSON object—no extra text, code fences, or commentary.\n\n"
        "=== DEPENDENCIES (for context) ===\n"
        f"{json.dumps(deps_summary, ensure_ascii=False)}\n\n"
        "=== JSON SCHEMA (authoritative) ===\n"
        f"{json.dumps(json_schema, ensure_ascii=False)}\n\n"
        "REQUIREMENTS:\n"
        " - Emit one valid JSON object conforming to the schema.\n"
        " - Do not include any wrapper keys like 'result' or 'data'.\n"
        " - No markdown, no backticks, no explanations.\n"
        " - Do not add any properties that are not defined in the schema.\n"
    )
    if strict_json:
        usr += " - STRICT: Any deviation from the schema is an error.\n"

    return usr, json_schema


def _parse_json_strict(text: str) -> Dict[str, Any]:
    """
    Best-effort JSON extraction. We do NOT allow prose.
    """
    text = (text or "").strip()
    # Common case: pure JSON
    if text.startswith("{") and text.endswith("}"):
        return json.loads(text)
    # Some providers may wrap in code fences inadvertently; strip once.
    if "```" in text:
        parts = text.split("```")
        # try last JSON-looking chunk
        candidates = [p.strip() for p in parts if p.strip().startswith("{") and p.strip().endswith("}")]
        if candidates:
            return json.loads(candidates[-1])
    # Fallback attempt
    return json.loads(text)


async def _with_retry(coro_factory, *, max_attempts: int, backoff_ms: int, jitter_ms: int) -> Any:
    attempt = 0
    last_exc: Optional[Exception] = None
    while attempt < max_attempts:
        try:
            return await coro_factory()
        except Exception as e:
            last_exc = e
            attempt += 1
            if attempt >= max_attempts:
                break
            delay = (backoff_ms / 1000.0)
            if jitter_ms:
                import random
                delay += random.uniform(0, jitter_ms / 1000.0)
            await asyncio.sleep(delay)
    assert last_exc is not None
    raise last_exc


# ------------- node -------------
def llm_execution_node(*, runs_repo: RunRepository):
    secret_resolver = SecretResolver()

    async def _node(
        state: Dict[str, Any]
    ) -> Command[Literal["capability_executor"]] | Dict[str, Any]:
        run_doc = state["run"]
        run_uuid = UUID(run_doc["run_id"])
        dispatch = state.get("dispatch") or {}
        step = dispatch.get("step") or {}
        capability = dispatch.get("capability") or {}
        step_id = step.get("id") or state.get("current_step_id") or "<unknown-step>"
        cap_id = capability.get("id") or "<unknown-cap>"

        started = datetime.now(timezone.utc)

        # Artifact kinds available in graph state (from input_resolver)
        kinds_map: Dict[str, Dict[str, Any]] = state.get("artifact_kinds") or {}
        # Determine which artifact kinds we must produce
        produces_kinds: List[str] = capability.get("produces_kinds") or []

        # --- Upfront visibility of artifact_kinds and plan
        try:
            kinds_catalog_preview = [
                {
                    "id": k,
                    "latest": (v or {}).get("latest_schema_version"),
                    "has_prompt_system": bool(
                        next(
                            (
                                sv.get("prompt", {}).get("system")
                                for sv in (v or {}).get("schema_versions", [])
                                if sv.get("version") == (v or {}).get("latest_schema_version")
                            ),
                            None,
                        )
                    ),
                }
                for k, v in kinds_map.items()
            ]
            missing_for_step = [k for k in produces_kinds if k not in kinds_map]
            logger.info(
                "[llm] start step_id=%s cap_id=%s produces=%s missing_kinds=%s kinds_in_state=%d",
                step_id, cap_id, produces_kinds, missing_for_step, len(kinds_map),
            )
            logger.info("[llm] artifact_kinds.catalog %s", _json_preview(kinds_catalog_preview, 1200))
        except Exception:
            logger.exception("[llm] failed to log artifact_kinds catalog")

        # Pull LLM config
        exec_cfg = (capability.get("execution") or {}).get("llm_config") or {}
        provider = exec_cfg.get("provider")
        model = exec_cfg.get("model")
        base_url = exec_cfg.get("base_url")
        organization = exec_cfg.get("organization")
        headers = dict(exec_cfg.get("headers") or {})
        query_params = dict(exec_cfg.get("query_params") or {})
        timeout_sec = int(exec_cfg.get("timeout_sec") or 60)
        retry_policy = exec_cfg.get("retry") or {}
        params = (exec_cfg.get("parameters") or {})
        auth_alias = exec_cfg.get("auth")

        temperature = params.get("temperature")
        top_p = params.get("top_p")
        max_tokens = params.get("max_tokens")

        max_attempts = int(retry_policy.get("max_attempts", 2))
        backoff_ms = int(retry_policy.get("backoff_ms", 250))
        jitter_ms = int(retry_policy.get("jitter_ms", 50))

        logger.info(
            "[llm] config provider=%s model=%s base=%s timeout_s=%s temp=%s top_p=%s max_tokens=%s retries=%s",
            provider,
            model,
            (base_url or "")[:80],
            timeout_sec,
            temperature,
            top_p,
            max_tokens,
            {"max_attempts": max_attempts, "backoff_ms": backoff_ms, "jitter_ms": jitter_ms},
        )

        # Resolve auth now (alias -> secret)
        try:
            resolved_auth = secret_resolver.resolve_auth(auth_alias)
        except Exception as e:
            err = f"LLM auth resolution failed: {e}"
            logger.error("[llm] %s", err)
            await runs_repo.append_step_audit(
                run_uuid,
                StepAudit(
                    step_id=step_id,
                    capability_id=cap_id,
                    mode="llm",
                    inputs_preview={"error": "auth resolution failed"},
                    calls=[
                        ToolCallAudit(
                            system_prompt=None,
                            user_prompt=None,
                            llm_config=exec_cfg,
                            raw_output_sample=str(e)[:400],
                            status="error",
                        )
                    ],
                ),
            )
            await runs_repo.step_failed(run_uuid, step_id, error=err)
            return Command(goto="capability_executor", update={"dispatch": {}, "last_mcp_error": err})

        # Build provider adapter
        try:
            adapter: ExecLLM = build_exec_llm(
                provider=provider,
                model=model,
                base_url=base_url,
                organization=organization,
                headers=headers,
                query_params=query_params,
                timeout_sec=timeout_sec,
                auth=resolved_auth,
            )
            logger.info("[llm] adapter ready provider=%s model=%s", provider, model)
        except Exception as e:
            err = f"LLM adapter construction failed: {e}"
            logger.error("[llm] %s", err)
            await runs_repo.append_step_audit(
                run_uuid,
                StepAudit(
                    step_id=step_id,
                    capability_id=cap_id,
                    mode="llm",
                    inputs_preview={"error": "adapter construction failed"},
                    calls=[
                        ToolCallAudit(
                            system_prompt=None,
                            user_prompt=None,
                            llm_config=exec_cfg,
                            raw_output_sample=str(e)[:400],
                            status="error",
                        )
                    ],
                ),
            )
            await runs_repo.step_failed(run_uuid, step_id, error=err)
            return Command(goto="capability_executor", update={"dispatch": {}, "last_mcp_error": err})

        # Execute per target kind
        staged_before = list(state.get("staged_artifacts") or [])
        produced: List[Dict[str, Any]] = []
        call_audits: List[ToolCallAudit] = []

        # visibility: what inputs are we about to pass into prompts?
        try:
            _ri = ((state.get("request") or {}).get("inputs") or {})
            ri_keys = list(_ri.keys())
            ri_size = len(json.dumps(_ri, ensure_ascii=False))
            logger.info("[llm] run_inputs keys=%s approx_size_bytes=%d", ri_keys, ri_size)
        except Exception:
            logger.exception("[llm] failed to log run_inputs overview")

        try:
            for kind_id in produces_kinds:
                kind_spec = kinds_map.get(kind_id) or {}
                schema_entry = _latest_schema_entry(kind_spec)
                if not schema_entry:
                    # Hard error: cannot produce without schema/prompt
                    msg = f"Artifact kind '{kind_id}' is missing schema_versions."
                    logger.error("[llm] %s", msg)
                    call_audits.append(
                        ToolCallAudit(
                            system_prompt=None,
                            user_prompt=None,
                            llm_config=exec_cfg,
                            raw_output_sample=msg,
                            status="error",
                        )
                    )
                    continue

                prompt_meta = schema_entry.get("prompt") or {}
                system_prompt = prompt_meta.get("system") or "Generate the artifact strictly as JSON per the schema."

                depends_on = schema_entry.get("depends_on") or {}
                dep_payload = _collect_dependencies(staged_before + produced, depends_on)

                user_prompt, json_schema = _mk_user_prompt(kind_id, schema_entry, dep_payload)

                # >>> Append RUN INPUTS to the user prompt (authoritative request inputs: avc/fss/pss/etc.)
                try:
                    run_inputs = ((state.get("request") or {}).get("inputs") or {})

                    def _clip(s: str, n: int = 24000) -> str:
                        try:
                            return s if len(s) <= n else (s[:n] + "…")
                        except Exception:
                            return s

                    user_prompt += (
                        "\n\n=== RUN INPUTS (authoritative, from request.inputs) ===\n"
                        + _clip(json.dumps(run_inputs, ensure_ascii=False))
                        + "\n"
                    )
                    logger.info(
                        "[llm] appended run_inputs to prompt kind=%s inputs_keys=%d",
                        kind_id,
                        len(list(run_inputs.keys())),
                    )
                except Exception:
                    # Non-fatal; proceed without RUN INPUTS if something goes wrong
                    logger.exception("[llm] failed to append RUN INPUTS for kind=%s", kind_id)

                # Per-kind visibility
                try:
                    logger.info(
                        "[llm] kind=%s schema_ver=%s depends_hard=%s depends_soft=%s",
                        kind_id,
                        schema_entry.get("version"),
                        list((depends_on or {}).get("hard") or []),
                        list((depends_on or {}).get("soft") or []),
                    )
                    logger.info(
                        "[llm] prompts kind=%s system.len=%d user.len=%d dep_keys=%d",
                        kind_id,
                        len(system_prompt or ""),
                        len(user_prompt or ""),
                        len(dep_payload.keys()),    
                    )
                    logger.debug("[llm] system(kind=%s) %s", kind_id, _json_preview(system_prompt))
                    logger.debug("[llm] user(kind=%s) %s", kind_id, _json_preview(user_prompt, 1800))
                except Exception:
                    logger.exception("[llm] logging prompts failed kind=%s", kind_id)

                async def _do():
                    return await adapter.acomplete(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        temperature=temperature,
                        top_p=top_p,
                        max_tokens=max_tokens,
                    )

                call_started = datetime.now(timezone.utc)
                try:
                    result = await _with_retry(
                        _do,
                        max_attempts=max_attempts,
                        backoff_ms=backoff_ms,
                        jitter_ms=jitter_ms,
                    )
                    raw_text = result.text or ""
                    duration_ms = int((datetime.now(timezone.utc) - call_started).total_seconds() * 1000)
                    logger.info("[llm] result kind=%s tokens_len~=%s duration_ms=%d", kind_id, len(raw_text), duration_ms)
                    logger.debug("[llm] raw(kind=%s) %s", kind_id, _json_preview(raw_text, 2000))

                    # Parse & validate JSON
                    try:
                        data_obj = _parse_json_strict(raw_text)
                        logger.info("[llm] parse_ok kind=%s", kind_id)
                    except Exception as pe:
                        # Parsing error -> audit + skip this kind
                        call_audits.append(
                            ToolCallAudit(
                                system_prompt=system_prompt,
                                user_prompt=user_prompt,
                                llm_config=exec_cfg,
                                raw_output_sample=(str(pe)[:400]),
                                status="error",
                            )
                        )
                        logger.error("[llm] JSON parse failed for %s: %s", kind_id, pe)
                        continue

                    # Validate against kind schema when available
                    validation_errors: List[str] = []
                    if json_schema:
                        try:
                            Draft202012Validator(json_schema).validate(data_obj)
                        except ValidationError as ve:
                            validation_errors.append(ve.message)
                            logger.warning("[llm] schema_validation_failed kind=%s err=%s", kind_id, ve.message)
                        else:
                            logger.info("[llm] schema_validation_ok kind=%s", kind_id)

                    call_audits.append(
                        ToolCallAudit(
                            system_prompt=system_prompt,
                            user_prompt=user_prompt,
                            llm_config=exec_cfg,
                            raw_output_sample=(raw_text[:800]),
                            validation_errors=validation_errors,
                            duration_ms=duration_ms,
                            status="ok" if not validation_errors else "failed",
                        )
                    )

                    # Only stage if valid (or no schema to validate against)
                    if not validation_errors:
                        produced.append(
                            {
                                "kind": kind_id,
                                "data": data_obj,
                                "produced_in_step_id": step_id,  # <-- tag for strict enrichment scoping
                                "provenance": {
                                    "step_id": step_id,
                                    "capability_id": cap_id,
                                    "mode": "llm",
                                },
                            }
                        )
                        logger.info("[llm] staged kind=%s staged_count_now=%d", kind_id, len(staged_before) + len(produced))
                except Exception as e:
                    duration_ms = int((datetime.now(timezone.utc) - call_started).total_seconds() * 1000)
                    call_audits.append(
                        ToolCallAudit(
                            system_prompt=system_prompt,
                            user_prompt=user_prompt,
                            llm_config=exec_cfg,
                            raw_output_sample=str(e)[:800],
                            duration_ms=duration_ms,
                            status="error",
                        )
                    )
                    logger.exception("[llm] execution failed for kind %s", kind_id)

            # Append tool-call audits and mark step completion/failure
            if call_audits:
                await runs_repo.append_step_audit(
                    run_uuid,
                    StepAudit(
                        step_id=step_id,
                        capability_id=cap_id,
                        mode="llm",
                        inputs_preview={
                            "produces_kinds": produces_kinds,
                            "request_inputs_keys": list(((state.get("request") or {}).get("inputs") or {}).keys()),
                        },
                        calls=call_audits,
                    ),
                )

            if not produced:
                # Non-terminal: mark the step failed but allow graph to continue.
                err = "LLM produced no valid artifacts"
                logger.error("[llm] %s step_id=%s cap_id=%s (continuing to next step; non-terminal)", err, step_id, cap_id)
                await runs_repo.step_failed(run_uuid, step_id, error=err)
                return Command(
                    goto="capability_executor",
                    update={
                        "dispatch": {},
                        "last_mcp_summary": {
                            "tool_calls": [
                                {
                                    "name": "llm.generate",
                                    "status": "failed",
                                    "duration_ms": None,
                                }
                            ],
                            "artifact_count": 0,
                            "completed_step_id": step_id,
                            "pages_fetched": 0,
                        },
                        # IMPORTANT: do not set last_mcp_error here so router doesn't terminate the run
                        "last_mcp_error": None,
                    },
                )

            # Success path
            duration_ms_total = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
            logger.info(
                "[llm] handoff step_id=%s cap_id=%s produced=%d duration_ms=%d",
                step_id, cap_id, len(produced), duration_ms_total
            )
            await runs_repo.step_completed(
                run_uuid,
                step_id,
                metrics={"mode": "llm", "duration_ms": duration_ms_total, "artifact_count": len(produced)},
            )

            # Handoff mirroring MCP breadcrumbs so router transitions to enrichment
            return Command(
                goto="capability_executor",
                update={
                    "dispatch": {},
                    "staged_artifacts": (state.get("staged_artifacts") or []) + produced,
                    "last_mcp_summary": {
                        "tool_calls": [
                            {
                                "name": "llm.generate",
                                "status": c.status,
                                "duration_ms": getattr(c, "duration_ms", None),
                            }
                            for c in call_audits
                        ],
                        "artifact_count": len(produced),
                        "completed_step_id": step_id,
                        "pages_fetched": 0,
                    },
                    "last_mcp_error": None,
                },
            )

        except Exception as e:
            err = f"LLM execution error: {e}"
            logger.exception("[llm] error step_id=%s cap_id=%s msg=%s", step_id, cap_id, err)
            await runs_repo.append_step_audit(
                run_uuid,
                StepAudit(
                    step_id=step_id,
                    capability_id=cap_id,
                    mode="llm",
                    inputs_preview={"produces_kinds": capability.get("produces_kinds") or []},
                    calls=[
                        ToolCallAudit(
                            system_prompt=None,
                            user_prompt=None,
                            llm_config=exec_cfg,
                            raw_output_sample=str(e)[:800],
                            status="failed",
                        )
                    ],
                ),
            )
            await runs_repo.step_failed(run_uuid, step_id, error=err)
            return Command(goto="capability_executor", update={"dispatch": {}, "last_mcp_error": err})

    return _node