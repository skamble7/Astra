# app/agent/nodes/mcp_input_resolver.py
from __future__ import annotations

import json
import logging
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

def _cap_io_input_schema(capability: Dict[str, Any]) -> Dict[str, Any]:
    return (((capability.get("execution") or {}).get("io") or {}).get("input_schema") or {})

def _tool_calls(capability: Dict[str, Any]) -> List[Dict[str, Any]]:
    return (((capability.get("execution") or {}).get("tool_calls")) or [])

def _choose_tool_name(capability: Dict[str, Any]) -> str:
    calls = _tool_calls(capability)
    if not calls:
        return ""
    if len(calls) == 1:
        return str(calls[0].get("tool") or "")
    # If multiple, pick the first deterministically (tool disambiguation can be added later)
    return str(calls[0].get("tool") or "")

def _first_required_props(schema: Dict[str, Any]) -> List[str]:
    req = schema.get("required")
    return list(req) if isinstance(req, list) else []

def _upstream_kind_ids_for_capability(capability: Dict[str, Any], artifact_kinds: Dict[str, Dict[str, Any]]) -> List[str]:
    """
    Given the capability's produces_kinds, collect all 'depends_on' kinds (hard and soft)
    from those kind specs. This tells us which previously-produced artifacts are relevant
    inputs for the next step.
    """
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

def _collect_relevant_artifacts_for_later_step(
    *,
    state: Dict[str, Any],
    capability: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Return artifacts prioritized by whether their 'kind' matches the upstream depends_on
    kinds of the capability's produces_kinds. Falls back to all artifacts if none match.
    """
    artifacts: List[Dict[str, Any]] = state.get("mcp_artifacts") or []
    if not artifacts:
        return []

    art_kinds_map: Dict[str, Dict[str, Any]] = state.get("artifact_kinds") or {}
    upstream = set(_upstream_kind_ids_for_capability(capability, art_kinds_map))
    if not upstream:
        return artifacts[:]  # nothing to prioritize against

    prioritized: List[Dict[str, Any]] = []
    others: List[Dict[str, Any]] = []
    for a in artifacts:
        k = a.get("kind") or a.get("_kind") or a.get("artifact_kind") or a.get("type")
        (prioritized if isinstance(k, str) and k in upstream else others).append(a)
    return prioritized + others

def _truncate_json(obj: Any, max_chars: int) -> str:
    s = json.dumps(obj, ensure_ascii=False)
    return s if len(s) <= max_chars else s[: max_chars - 3] + "..."

# ---------- LLM prompts ----------

def _build_prompt_step0(
    *,
    pack_input_schema: Dict[str, Any],
    pack_inputs: Dict[str, Any],
    capability: Dict[str, Any],
    tool_input_schema: Dict[str, Any],
    step: Dict[str, Any],
) -> str:
    cap_name = capability.get("name") or capability.get("id") or "<capability>"
    return (
        "You are resolving arguments for calling an MCP tool.\n"
        "Goal: Construct a JSON object of arguments that VALIDATES against the MCP tool's input JSON Schema.\n\n"
        "Important rules:\n"
        "1) Use EXACT property names/types as defined in the MCP tool input schema.\n"
        "2) Prefer values found in the Pack Input VALUES (not the schema) when they are relevant.\n"
        "3) You may map differently named fields (e.g., repository.gitUrl → repo_url) based on meaning.\n"
        "4) Do NOT fabricate values that contradict Pack Input values. If a required value cannot be inferred, make a best, minimal guess consistent with both schemas.\n"
        "5) Omit fields that are not in the MCP tool schema.\n"
        "6) The output must be ONLY the JSON object. No commentary.\n\n"
        f"Capability: {cap_name}\n"
        f"Step params (hints only): {_truncate_json(step.get('params') or {}, 2000)}\n\n"
        "Pack Input SCHEMA:\n"
        f"{_truncate_json(pack_input_schema or {}, 4000)}\n\n"
        "Pack Input VALUES:\n"
        f"{_truncate_json(pack_inputs or {}, 4000)}\n\n"
        "MCP Tool Input JSON Schema:\n"
        f"{_truncate_json(tool_input_schema or {}, 4000)}\n\n"
        "Return ONLY the JSON object of tool args."
    )

def _build_prompt_later_step(
    *,
    capability: Dict[str, Any],
    tool_input_schema: Dict[str, Any],
    step: Dict[str, Any],
    artifacts: List[Dict[str, Any]],
    artifact_kinds: Dict[str, Any],
) -> str:
    cap_name = capability.get("name") or capability.get("id") or "<capability>"
    return (
        "You are resolving arguments for calling an MCP tool for a LATER step in a playbook.\n"
        "Goal: Construct a JSON object of arguments that VALIDATES against the MCP tool's input JSON Schema.\n\n"
        "Important rules:\n"
        "1) Use EXACT property names/types as defined in the MCP tool input schema.\n"
        "2) Use upstream artifacts as the primary source of truth. Start from kinds listed in the capability's produces_kinds,\n"
        "   then inspect their 'depends_on' kinds to find relevant upstream artifacts. Prefer data fields clearly matching\n"
        "   required properties (e.g., repo snapshot → paths_root, branch, commit).\n"
        "3) Do NOT invent values that conflict with artifact data; when in doubt, leave optional fields out.\n"
        "4) Omit fields that are not in the MCP tool schema.\n"
        "5) The output must be ONLY the JSON object. No commentary.\n\n"
        f"Capability: {cap_name}\n"
        f"Step params (hints only): {_truncate_json(step.get('params') or {}, 2000)}\n\n"
        "Artifact Kind Specs (relevant excerpts):\n"
        f"{_truncate_json(artifact_kinds or {}, 3000)}\n\n"
        "Relevant Upstream Artifacts (snippets):\n"
        f"{_truncate_json(artifacts[:10], 6000)}\n\n"
        "MCP Tool Input JSON Schema:\n"
        f"{_truncate_json(tool_input_schema or {}, 4000)}\n\n"
        "Return ONLY the JSON object of tool args."
    )

# ---------- Node ----------

def mcp_input_resolver_node(
    *,
    runs_repo: RunRepository,
    llm: AgentLLM,
):
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

        # 1) Choose tool
        tool_name = _choose_tool_name(capability)
        if not tool_name:
            msg = f"No MCP tools found/selected for capability '{cap_id}'."
            await runs_repo.step_failed(run_uuid, step_id, error=msg)
            # Advance the graph so we don't loop on a dead step
            return Command(goto="capability_executor", update={"step_idx": step_idx + 1, "current_step_id": None})

        # 2) Schemas & validator
        tool_input_schema = _cap_io_input_schema(capability) or {"type": "object", "properties": {}, "additionalProperties": True}
        validator = Draft202012Validator(tool_input_schema)

        # 3) Build LLM prompt (step 0 vs later)
        llm_calls: List[ToolCallAudit] = []
        prompt: str
        schema_for_args = {"name": "mcp_tool_args", "schema": {"type": "object", "properties": {}, "additionalProperties": True}}

        if step_idx == 0:
            pack = state.get("pack") or {}
            pack_input_schema = (((pack.get("pack_input") or {}).get("json_schema")) or {})
            pack_inputs = ((state.get("request") or {}).get("inputs")) or {}
            prompt = _build_prompt_step0(
                pack_input_schema=pack_input_schema,
                pack_inputs=pack_inputs,
                capability=capability,
                tool_input_schema=tool_input_schema,
                step=step,
            )
        else:
            artifacts = _collect_relevant_artifacts_for_later_step(state=state, capability=capability)
            artifact_kinds = state.get("artifact_kinds") or {}
            prompt = _build_prompt_later_step(
                capability=capability,
                tool_input_schema=tool_input_schema,
                step=step,
                artifacts=artifacts,
                artifact_kinds=artifact_kinds,
            )

        # 4) LLM → candidate args
        llm_started = datetime.now(timezone.utc)
        resp = await llm.acomplete_json(prompt, schema=schema_for_args)
        llm_duration = int((datetime.now(timezone.utc) - llm_started).total_seconds() * 1000)

        try:
            candidate = json.loads(resp.text or "{}")
        except Exception:
            candidate = {}

        # 5) Validate & (if needed) attempt a single repair
        resolved_args = candidate
        err_msg: Optional[str] = None
        try:
            validator.validate(resolved_args)
            # Ensure all required are present
            missing = [r for r in _first_required_props(tool_input_schema) if r not in resolved_args]
            if missing:
                raise ValidationError(f"Missing required field(s): {', '.join(missing)}")
        except ValidationError as ve:
            err_msg = ve.message
            repair_prompt = (
                "Fix the JSON args so they satisfy the JSON Schema exactly.\n\n"
                f"Schema:\n{_truncate_json(tool_input_schema, 4000)}\n\n"
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
            try:
                validator.validate(repaired)
                missing = [r for r in _first_required_props(tool_input_schema) if r not in repaired]
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
                        "schema": tool_input_schema,
                        "llm_candidate": candidate,
                    },
                    calls=llm_calls,
                ),
            )
            await runs_repo.step_failed(run_uuid, step_id, error=msg)
            # Advance the graph to avoid loops
            return Command(goto="capability_executor", update={"step_idx": step_idx + 1, "current_step_id": None})

        # 6) Audit success
        await runs_repo.append_step_audit(
            run_uuid,
            StepAudit(
                step_id=step_id,
                capability_id=cap_id,
                mode="mcp",
                inputs_preview={"phase": "input-resolver", "tool_name": tool_name, "resolved_args": resolved_args},
                calls=llm_calls or [],
            ),
        )

        # 7) Handoff to execution (IMPORTANT: do NOT override step_idx here to avoid recursion loops)
        update = {
            # Leave step_idx management to the executor node
            "current_step_id": step_id,
            "dispatch": {
                "capability": capability,
                "step": step,
                "resolved": {"tool_name": tool_name, "args": resolved_args},
            },
        }
        return Command(goto="mcp_execution", update=update)

    return _node