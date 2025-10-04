from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from typing_extensions import Literal
from langgraph.types import Command
from jsonschema import Draft202012Validator, ValidationError

from app.db.run_repository import RunRepository
from app.llm.base import AgentLLM
from app.models.run_models import StepAudit, ToolCallAudit

logger = logging.getLogger("app.agent.nodes.mcp_input_resolver")

# ---------- Utilities ----------
def _cap_io_input_contract(capability: Dict[str, Any]) -> Dict[str, Any]:
    return (((capability.get("execution") or {}).get("io") or {}).get("input_contract") or {})

def _cap_io_input_json_schema(capability: Dict[str, Any]) -> Dict[str, Any]:
    return (_cap_io_input_contract(capability).get("json_schema") or {})

def _cap_io_input_schema_guide(capability: Dict[str, Any]) -> str:
    guide = _cap_io_input_contract(capability).get("schema_guide")
    return str(guide) if isinstance(guide, str) else ""

def _tool_calls(capability: Dict[str, Any]) -> List[Dict[str, Any]]:
    return (((capability.get("execution") or {}).get("tool_calls")) or [])

def _choose_tool_name(capability: Dict[str, Any]) -> str:
    calls = _tool_calls(capability)
    if not calls:
        return ""
    if len(calls) == 1:
        return str(calls[0].get("tool") or "")
    return str(calls[0].get("tool") or "")

def _first_required_props(schema: Dict[str, Any]) -> List[str]:
    req = schema.get("required")
    return list(req) if isinstance(req, list) else []

def _upstream_kind_ids_for_capability(capability: Dict[str, Any], artifact_kinds: Dict[str, Dict[str, Any]]) -> List[str]:
    produces = capability.get("produces_kinds") or []
    upstream: List[str] = []
    for k in produces:
        spec = artifact_kinds.get(k) or {}
        deps = (spec.get("depends_on") or {})
        for branch in ("hard", "soft"):
            for dep in (deps.get(branch) or []):
                if dep not in upstream:
                    upstream.append(dep)
    return upstream

def _collect_relevant_artifacts_for_later_step(*, state: Dict[str, Any], capability: Dict[str, Any]) -> List[Dict[str, Any]]:
    artifacts: List[Dict[str, Any]] = state.get("mcp_artifacts") or []
    if not artifacts:
        return []
    art_kinds_map: Dict[str, Dict[str, Any]] = state.get("artifact_kinds") or {}
    upstream = set(_upstream_kind_ids_for_capability(capability, art_kinds_map))
    if not upstream:
        return artifacts[:]
    prioritized: List[Dict[str, Any]] = []
    others: List[Dict[str, Any]] = []
    for a in artifacts:
        k = a.get("kind") or a.get("_kind") or a.get("artifact_kind") or a.get("type")
        (prioritized if isinstance(k, str) and k in upstream else others).append(a)
    return prioritized + others

def _truncate_json(obj: Any, max_chars: int) -> str:
    try:
        s = json.dumps(obj, ensure_ascii=False)
    except Exception:
        s = "<unserializable>"
    return s if len(s) <= max_chars else s[: max_chars - 3] + "..."

# ---------- LLM prompts ----------
def _build_prompt_step0(*, pack_input_schema: Dict[str, Any], pack_inputs: Dict[str, Any], capability: Dict[str, Any], exec_input_json_schema: Dict[str, Any], exec_input_schema_guide: str, step: Dict[str, Any]) -> str:
    cap_name = capability.get("name") or capability.get("id") or "<capability>"
    guide_block = f"\nExecution Input – schema_guide (human-readable):\n{exec_input_schema_guide}\n" if exec_input_schema_guide else ""
    return (
        "You are resolving arguments for calling an MCP tool.\n"
        "Goal: Construct a JSON object of arguments that VALIDATES against the capability's ExecutionInput JSON Schema.\n\n"
        "Important rules:\n"
        "1) Use EXACT property names/types as defined in the ExecutionInput JSON Schema.\n"
        "2) Prefer values found in the Pack Input VALUES when relevant; map semantically equivalent names "
        "(e.g., repository.gitUrl → repo_url).\n"
        "3) Do NOT fabricate values that contradict Pack Input values. If a required value cannot be inferred, make a minimal, "
        "reasonable guess consistent with both schemas and the schema_guide.\n"
        "4) Omit fields that are not in the ExecutionInput schema.\n"
        "5) If the schema includes 'page_size' or 'cursor', include them. Use the schema_guide defaults when present.\n"
        "6) The output must be ONLY the JSON object (no commentary).\n\n"
        f"Capability: {cap_name}\n"
        f"Step params (hints only): {_truncate_json(step.get('params') or {}, 2000)}\n"
        f"{guide_block}\n"
        "Pack Input SCHEMA:\n"
        f"{_truncate_json(pack_input_schema or {}, 4000)}\n\n"
        "Pack Input VALUES:\n"
        f"{_truncate_json(pack_inputs or {}, 4000)}\n\n"
        "Execution Input JSON Schema (input_contract.json_schema):\n"
        f"{_truncate_json(exec_input_json_schema or {}, 4000)}\n\n"
        "Return ONLY the JSON object of tool args."
    )

def _build_prompt_later_step(*, capability: Dict[str, Any], exec_input_json_schema: Dict[str, Any], exec_input_schema_guide: str, step: Dict[str, Any], artifacts: List[Dict[str, Any]], artifact_kinds: Dict[str, Any]) -> str:
    cap_name = capability.get("name") or capability.get("id") or "<capability>"
    guide_block = f"\nExecution Input – schema_guide (human-readable):\n{exec_input_schema_guide}\n" if exec_input_schema_guide else ""
    return (
        "You are resolving arguments for calling an MCP tool for a LATER step in a playbook.\n"
        "Goal: Construct a JSON object of arguments that VALIDATES against the capability's ExecutionInput JSON Schema.\n\n"
        "Important rules:\n"
        "1) Use EXACT property names/types as defined in the ExecutionInput JSON Schema.\n"
        "2) Use upstream artifacts as the primary source of truth. Start from kinds listed in the capability's produces_kinds,\n"
        "   then inspect their 'depends_on' kinds to find relevant upstream artifacts. Prefer data fields clearly matching\n"
        "   required properties (e.g., repo snapshot → paths_root, branch, commit), and follow schema_guide for mapping tips.\n"
        "3) Do NOT invent values that conflict with artifact data; when in doubt, leave optional fields out.\n"
        "4) Omit fields that are not in the ExecutionInput schema.\n"
        "5) If the schema includes 'page_size' or 'cursor', include them. Use the schema_guide defaults when present.\n"
        "6) The output must be ONLY the JSON object (no commentary).\n\n"
        f"Capability: {cap_name}\n"
        f"Step params (hints only): {_truncate_json(step.get('params') or {}, 2000)}\n"
        f"{guide_block}\n"
        "Artifact Kind Specs (relevant excerpts):\n"
        f"{_truncate_json(artifact_kinds or {}, 3000)}\n\n"
        "Relevant Upstream Artifacts (snippets):\n"
        f"{_truncate_json(artifacts[:10], 6000)}\n\n"
        "Execution Input JSON Schema (input_contract.json_schema):\n"
        f"{_truncate_json(exec_input_json_schema or {}, 4000)}\n\n"
        "Return ONLY the JSON object of tool args."
    )

_DEFAULT_NUM_RE = re.compile(r"Defaults?\s+to\s+(\d+)", re.IGNORECASE)

def _infer_default_from_guide(guide: str, key: str) -> Optional[int]:
    if not guide or not key:
        return None
    m = _DEFAULT_NUM_RE.search(guide)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return None
    return None

def _postprocess_args_with_heuristics(*, candidate: Dict[str, Any], capability: Dict[str, Any], step: Dict[str, Any], exec_input_schema: Dict[str, Any], exec_input_schema_guide: str) -> Dict[str, Any]:
    args = dict(candidate or {})
    props = (exec_input_schema.get("properties") or {})

    if "page_size" in props and "page_size" not in args:
        step_params = step.get("params") or {}
        if isinstance(step_params, dict):
            for src_key in ("page_size", "file_limit", "pageSize", "files_per_page"):
                if isinstance(step_params.get(src_key), int) and step_params[src_key] >= 1:
                    args["page_size"] = int(step_params[src_key])
                    break
        if "page_size" not in args:
            guide_default = _infer_default_from_guide(exec_input_schema_guide, "page_size")
            if isinstance(guide_default, int) and guide_default >= 1:
                args["page_size"] = guide_default

    if "cursor" in props and "cursor" not in args:
        args["cursor"] = None

    if "kinds" in props and "kinds" not in args:
        produces = capability.get("produces_kinds") or []
        enum = None
        kinds_schema = props["kinds"]
        if isinstance(kinds_schema, dict) and isinstance(kinds_schema.get("items"), dict):
            enum = kinds_schema["items"].get("enum")
        if isinstance(enum, list) and enum:
            mapped = []
            for k in produces:
                suffix = k.split(".")[-1] if isinstance(k, str) else k
                if suffix in enum and suffix not in mapped:
                    mapped.append(suffix)
            if mapped:
                args["kinds"] = mapped

    return args

def mcp_input_resolver_node(*, runs_repo: RunRepository, llm: AgentLLM):
    async def _node(state: Dict[str, Any]) -> Command[Literal["mcp_execution", "capability_executor"]] | Dict[str, Any]:
        run = state["run"]
        run_uuid = UUID(run["run_id"])
        step_idx = int(state.get("step_idx", 0))
        dispatch = state.get("dispatch") or {}
        capability: Dict[str, Any] = dispatch.get("capability") or {}
        step: Dict[str, Any] = dispatch.get("step") or {}
        step_id = step.get("id") or "<unknown-step>"
        cap_id = capability.get("id") or "<unknown-cap>"

        started = datetime.now(timezone.utc)

        tool_name = _choose_tool_name(capability)
        if not tool_name:
            msg = f"No MCP tools found/selected for capability '{cap_id}'."
            await runs_repo.step_failed(run_uuid, step_id, error=msg)
            # IMPORTANT: do NOT write current_step_id here (avoid double-write with router)
            return Command(goto="capability_executor", update={"step_idx": step_idx + 1})

        exec_input_json_schema = _cap_io_input_json_schema(capability) or {
            "type": "object",
            "properties": {},
            "additionalProperties": True,
        }
        exec_input_schema_guide = _cap_io_input_schema_guide(capability)
        validator = Draft202012Validator(exec_input_json_schema)

        # Build prompt per step index
        llm_calls: List[ToolCallAudit] = []
        schema_for_args = {"name": "mcp_tool_args", "schema": {"type": "object", "properties": {}, "additionalProperties": True}}

        if step_idx == 0:
            pack = state.get("pack") or {}
            pack_input_schema = (((pack.get("pack_input") or {}).get("json_schema")) or {})
            pack_inputs = ((state.get("request") or {}).get("inputs")) or {}
            prompt = _build_prompt_step0(
                pack_input_schema=pack_input_schema,
                pack_inputs=pack_inputs,
                capability=capability,
                exec_input_json_schema=exec_input_json_schema,
                exec_input_schema_guide=exec_input_schema_guide,
                step=step,
            )
        else:
            artifacts = _collect_relevant_artifacts_for_later_step(state=state, capability=capability)
            artifact_kinds = state.get("artifact_kinds") or {}
            prompt = _build_prompt_later_step(
                capability=capability,
                exec_input_json_schema=exec_input_json_schema,
                exec_input_schema_guide=exec_input_schema_guide,
                step=step,
                artifacts=artifacts,
                artifact_kinds=artifact_kinds,
            )

        llm_started = datetime.now(timezone.utc)
        resp = await llm.acomplete_json(prompt, schema=schema_for_args)
        llm_duration = int((datetime.now(timezone.utc) - llm_started).total_seconds() * 1000)

        try:
            candidate = json.loads(resp.text or "{}")
        except Exception:
            candidate = {}

        candidate = _postprocess_args_with_heuristics(
            candidate=candidate,
            capability=capability,
            step=step,
            exec_input_schema=exec_input_json_schema,
            exec_input_schema_guide=exec_input_schema_guide,
        )

        resolved_args = candidate
        err_msg: Optional[str] = None
        try:
            validator.validate(resolved_args)
            missing = [r for r in _first_required_props(exec_input_json_schema) if r not in resolved_args]
            if missing:
                raise ValidationError(f"Missing required field(s): {', '.join(missing)}")
        except ValidationError as ve:
            err_msg = ve.message
            repair_prompt = (
                "Fix the JSON args so they satisfy the capability's ExecutionInput JSON Schema exactly.\n\n"
                f"ExecutionInput schema_guide:\n{exec_input_schema_guide}\n\n"
                f"ExecutionInput JSON Schema:\n{_truncate_json(exec_input_json_schema, 4000)}\n\n"
                f"Current args:\n{_truncate_json(resolved_args, 4000)}\n\n"
                f"Validation error: {err_msg}\n\n"
                "Return only the corrected JSON object."
            )
            repair_resp = await llm.acomplete_json(
                repair_prompt,
                schema={"name": "mcp_tool_args_repair", "schema": {"type": "object", "properties": {}, "additionalProperties": True}},
            )
            try:
                repaired = json.loads(repair_resp.text or "{}")
            except Exception:
                repaired = {}

            repaired = _postprocess_args_with_heuristics(
                candidate=repaired,
                capability=capability,
                step=step,
                exec_input_schema=exec_input_json_schema,
                exec_input_schema_guide=exec_input_schema_guide,
            )

            try:
                validator.validate(repaired)
                missing = [r for r in _first_required_props(exec_input_json_schema) if r not in repaired]
                if missing:
                    raise ValidationError(f"Missing required field(s): {', '.join(missing)}")
                resolved_args = repaired
                err_msg = None
            except ValidationError as ve2:
                err_msg = ve2.message

        llm_calls.append(
            ToolCallAudit(
                system_prompt=None,
                user_prompt=prompt[:8000],
                llm_config=capability.get("execution", {}).get("llm_config"),
                raw_output_sample=(resp.text or "")[:800],
                duration_ms=llm_duration,
                status="ok" if not err_msg else "failed",
                validation_errors=[err_msg] if err_msg else [],
            )
        )
        await runs_repo.append_tool_call_audit(run_uuid, step.get("id"), llm_calls[-1])

        if err_msg:
            msg = f"[MCP-INPUT] Failed to produce schema-valid args for {tool_name}: {err_msg}"
            logger.error(msg)
            await runs_repo.append_step_audit(
                run_uuid,
                StepAudit(
                    step_id=step_id,
                    capability_id=cap_id,
                    mode="mcp",
                    inputs_preview={
                        "phase": "input-resolver",
                        "tool_name": tool_name,
                        "execution_input_schema": exec_input_json_schema,
                        "schema_guide": exec_input_schema_guide,
                        "llm_candidate": candidate,
                    },
                    calls=llm_calls,
                ),
            )
            await runs_repo.step_failed(run_uuid, step_id, error=msg)
            # IMPORTANT: avoid writing current_step_id here
            return Command(goto="capability_executor", update={"step_idx": step_idx + 1})

        await runs_repo.append_step_audit(
            run_uuid,
            StepAudit(
                step_id=step_id,
                capability_id=cap_id,
                mode="mcp",
                inputs_preview={
                    "phase": "input-resolver",
                    "tool_name": tool_name,
                    "resolved_args": resolved_args,
                    "schema_guide_used": bool(exec_input_schema_guide),
                },
                calls=llm_calls or [],
            ),
        )

        # Handoff to execution WITHOUT touching current_step_id (router is the single writer)
        update = {
            "dispatch": {
                "capability": capability,
                "step": step,
                "resolved": {"tool_name": tool_name, "args": resolved_args},
            },
        }
        return Command(goto="mcp_execution", update=update)

    return _node