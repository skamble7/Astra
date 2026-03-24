# services/planner-service/app/agent/nodes/plan_input_resolver.py
"""
Plan Input Resolver node for the Execution Agent.

For step 0 (the data-ingestion step): uses pre-filled inputs from the
approved PlannerSession plan step (sourced from the input_contract form).

For steps 1+ (downstream steps): uses LLM-based resolution from staged
artifacts, identical to conductor_core's later-step logic (ADR-006).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict
from uuid import UUID

from jsonschema import Draft202012Validator, ValidationError
from typing_extensions import Literal
from langgraph.types import Command

from conductor_core.llm.base import AgentLLM
from conductor_core.protocols.repositories import RunRepositoryProtocol as RunRepository
from conductor_core.models.run_models import StepAudit
from conductor_core.nodes.mcp_input_resolver import (
    _get_tool_name,
    _collect_relevant_artifacts_for_later_step,
    _build_prompt_later_step,
    _postprocess_args_with_heuristics,
    _first_required_props,
)

logger = logging.getLogger("app.agent.nodes.plan_input_resolver")


def plan_input_resolver_node(*, runs_repo: RunRepository, llm: AgentLLM):
    async def _node(
        state: Dict[str, Any]
    ) -> Command[Literal["mcp_execution", "capability_executor"]] | Dict[str, Any]:
        run_doc = state["run"]
        run_uuid = UUID(run_doc["run_id"])
        step_idx = int(state.get("step_idx", 0))
        dispatch = state.get("dispatch") or {}
        step = dispatch.get("step") or {}
        capability = dispatch.get("capability") or {}
        step_id = step.get("id") or "<unknown-step>"
        cap_id = capability.get("id") or "<unknown-cap>"

        tool_name = _get_tool_name(capability)
        if not tool_name:
            err = f"No MCP tools configured for capability '{cap_id}'."
            logger.error("[plan_input_resolver] %s", err)
            await runs_repo.step_failed(run_uuid, step_id, error=err)
            return Command(
                goto="capability_executor",
                update={"dispatch": {}, "last_mcp_error": err, "step_idx": step_idx + 1},
            )

        if step_idx == 0:
            # ADR-006: step 0 uses user-confirmed inputs from the /run request (request["inputs"])
            args = dict((state.get("request") or {}).get("inputs") or {})
            logger.info(
                "[plan_input_resolver] step0_run_inputs step_id=%s tool=%s args_keys=%s",
                step_id, tool_name, list(args.keys()),
            )
            await runs_repo.append_step_audit(
                run_uuid,
                StepAudit(
                    step_id=step_id,
                    capability_id=cap_id,
                    mode="mcp",
                    inputs_preview={"source": "prefill", "tool_name": tool_name, "args_keys": list(args.keys())},
                    calls=[],
                ),
            )
        else:
            # ADR-006: steps 1+ resolve inputs from staged artifacts via LLM
            # Schema is discovered live at execution time via tools/list (no stored io contract).
            # Use an open schema here; the conductor's mcp_input_resolver does live validation.
            exec_input_json_schema: Dict[str, Any] = {
                "type": "object", "properties": {}, "additionalProperties": True,
            }
            exec_input_schema_guide = ""
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
            resp = await llm.acomplete_json(prompt, schema=exec_input_json_schema)
            try:
                candidate = json.loads(resp.text or "{}")
            except Exception:
                candidate = {}

            args = _postprocess_args_with_heuristics(
                candidate=candidate,
                capability=capability,
                step=step,
                exec_input_schema=exec_input_json_schema,
                exec_input_schema_guide=exec_input_schema_guide,
            )

            # Validate + repair (same pattern as conductor_core.nodes.mcp_input_resolver)
            validator = Draft202012Validator(exec_input_json_schema)
            err_msg = None
            try:
                validator.validate(args)
                missing = [r for r in _first_required_props(exec_input_json_schema) if r not in args]
                if missing:
                    raise ValidationError(f"Missing required field(s): {', '.join(missing)}")
            except ValidationError as ve:
                err_msg = ve.message
                repair_prompt = (
                    "Fix the JSON args so they satisfy the capability's ExecutionInput JSON Schema exactly.\n\n"
                    f"ExecutionInput schema_guide:\n{exec_input_schema_guide}\n\n"
                    f"ExecutionInput JSON Schema:\n{json.dumps(exec_input_json_schema)[:4000]}\n\n"
                    f"Current args:\n{json.dumps(args)[:4000]}\n\n"
                    f"Validation error: {err_msg}\n\n"
                    "Return only the corrected JSON object."
                )
                repair_resp = await llm.acomplete_json(
                    repair_prompt,
                    schema=exec_input_json_schema,
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
                    args = repaired
                    err_msg = None
                except ValidationError as ve2:
                    err_msg = ve2.message

            if err_msg:
                msg = f"[MCP-INPUT] Failed to produce schema-valid args for '{tool_name}': {err_msg}"
                logger.error(msg)
                await runs_repo.step_failed(run_uuid, step_id, error=msg)
                return Command(
                    goto="capability_executor",
                    update={"dispatch": {}, "last_mcp_error": msg, "step_idx": step_idx + 1},
                )

            logger.info(
                "[plan_input_resolver] later_step_resolved step_idx=%d step_id=%s tool=%s args_keys=%s",
                step_idx, step_id, tool_name, list(args.keys()),
            )
            await runs_repo.append_step_audit(
                run_uuid,
                StepAudit(
                    step_id=step_id,
                    capability_id=cap_id,
                    mode="mcp",
                    inputs_preview={
                        "source": "artifact_llm",
                        "tool_name": tool_name,
                        "args_keys": list(args.keys()),
                        "artifact_count": len(artifacts),
                    },
                    calls=[],
                ),
            )

        return Command(
            goto="mcp_execution",
            update={
                "dispatch": {
                    "capability": capability,
                    "step": step,
                    "resolved": {"tool_name": tool_name, "args": args},
                },
            },
        )

    return _node
