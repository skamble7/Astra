# services/planner-service/app/agent/nodes/plan_builder.py
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List
from uuid import uuid4

from conductor_core.llm.base import AgentLLM
from app.cache.manifest_cache import ManifestCache

logger = logging.getLogger("app.agent.nodes.plan_builder")

_SYSTEM_PROMPT = """You are the plan-builder component of ASTRA, a general-purpose capability orchestration platform.

ASTRA capabilities are registered execution units — they can do anything: parse COBOL, discover microservices architectures, modernize legacy code, generate API documentation, run security scans, fetch user stories, analyse domain models, and more. Each capability has a unique id, takes inputs, and produces typed artifact outputs.

Your job: given a set of selected capabilities and the user's goal, assemble an ordered execution pipeline. Pre-fill any step inputs you can infer from the conversation.

Respond ONLY with a single JSON object:
{
  "steps": [
    {
      "capability_id": "cap.xxx",
      "title": "Step title",
      "description": "What this step does",
      "inputs": {"key": "value"},
      "order": 1
    }
  ],
  "confidence": 0.85,
  "plan_summary": "Brief description of the overall plan"
}
"""

_MODIFY_SYSTEM_PROMPT = """You are the plan-builder component of ASTRA, a general-purpose capability orchestration platform.

ASTRA capabilities are registered execution units — they can do anything: parse COBOL, discover microservices architectures, modernize legacy code, generate API documentation, run security scans, etc.

An execution pipeline (plan) already exists. The user wants to modify it.

CRITICAL: You are the orchestrator — step removal, reordering, and addition are YOUR decisions, not something a capability does.
- "Remove the last step" → return the plan without the last step
- "Move step N to the front" → change the order values
- "Add a step for X" → insert a new step using the most suitable capability from the available list
- You do NOT need a capability that "edits plans" — YOU make the edit and return the updated JSON

Apply ONLY the changes the user requested. Preserve all other steps unchanged (same capability_id, title, description, inputs, order).

Respond ONLY with a single JSON object:
{
  "steps": [
    {
      "capability_id": "cap.xxx",
      "title": "Step title",
      "description": "What this step does",
      "inputs": {"key": "value"},
      "order": 1
    }
  ],
  "confidence": 0.90,
  "plan_summary": "Brief description of what changed"
}
"""


def plan_builder_node(*, llm: AgentLLM, cache: ManifestCache):
    async def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        intent = state.get("intent") or {}
        candidate_caps = state.get("candidate_capabilities") or []
        messages = state.get("messages") or []
        existing_plan = state.get("existing_plan") or []
        error = state.get("error")
        needs_clarification = state.get("needs_clarification", False)

        if error or needs_clarification:
            # If we have an existing plan, preserve it in state so the canvas doesn't go blank
            if existing_plan:
                return {
                    "draft_plan": existing_plan,
                    "confidence_score": 0.0,
                    "needs_clarification": True,
                    "clarification_question": state.get("clarification_question") or "Could you clarify your request?",
                    "response_message": state.get("clarification_question") or "Could you clarify your request?",
                }
            return {}

        if not candidate_caps:
            # If we have an existing plan, preserve it and ask for clarification
            result: Dict[str, Any] = {
                "confidence_score": 0.0,
                "needs_clarification": True,
                "clarification_question": "I couldn't identify the right capabilities for your request. Could you be more specific?",
            }
            if existing_plan:
                result["draft_plan"] = existing_plan
            else:
                result["draft_plan"] = []
            return result

        # Build capability summaries (without full execution config to keep prompt lean)
        caps_for_prompt = []
        for cap in candidate_caps:
            caps_for_prompt.append({
                "id": cap.get("id"),
                "title": cap.get("title") or cap.get("name"),
                "description": cap.get("description", ""),
                "produces_kinds": cap.get("produces_kinds", []),
                "execution_mode": (cap.get("execution") or {}).get("mode"),
                "input_contract": (((cap.get("execution") or {}).get("io") or {}).get("input_contract") or {}),
            })

        # Recent conversation context
        context_msgs = []
        for m in messages[-8:]:
            context_msgs.append(f"{m.get('role', 'user')}: {m.get('content', '')}")

        # ADR-009: if step 1 is MCP mode, append explicit input prefill instruction
        first_cap = caps_for_prompt[0] if caps_for_prompt else {}
        step1_mcp_block = ""
        if first_cap.get("execution_mode") == "mcp" and first_cap.get("input_contract"):
            step1_mcp_block = (
                "\n\nIMPORTANT — Step 1 input prefill (ADR-009):\n"
                "Step 1 is an MCP capability with an input_contract form. "
                "Extract any values the user mentioned in the conversation (URLs, repo names, branch names, file paths, etc.) "
                "and pre-fill the 'inputs' dict for step 1 using the input_contract field names exactly. "
                "Pre-filled values will be shown to the user for review before execution — if uncertain, make a best-effort guess."
            )

        if existing_plan:
            # Modification mode: user is refining an existing plan
            existing_steps_for_prompt = [
                {
                    "step_id": s.get("step_id"),
                    "capability_id": s.get("capability_id"),
                    "title": s.get("title"),
                    "description": s.get("description"),
                    "inputs": s.get("inputs") or {},
                    "order": s.get("order"),
                }
                for s in existing_plan
            ]
            prompt = (
                f"{_MODIFY_SYSTEM_PROMPT}\n\n"
                f"Current plan ({len(existing_plan)} steps):\n{json.dumps(existing_steps_for_prompt, indent=2)}\n\n"
                f"Available capabilities:\n{json.dumps(caps_for_prompt, indent=2)}\n\n"
                f"User request: {intent.get('description', state.get('current_message', ''))}\n\n"
                f"Conversation context:\n{''.join(context_msgs)}\n\n"
                f"Apply the user's requested modifications to the plan.{step1_mcp_block}"
            )
        else:
            # Fresh build: first message for this session
            prompt = (
                f"{_SYSTEM_PROMPT}\n\n"
                f"User intent: {json.dumps(intent, indent=2)}\n\n"
                f"Selected capabilities:\n{json.dumps(caps_for_prompt, indent=2)}\n\n"
                f"Conversation context:\n{''.join(context_msgs)}\n\n"
                f"Build the execution plan with pre-filled inputs.{step1_mcp_block}"
            )

        try:
            result = await llm.acomplete(prompt)
            text = (result.text or "").strip()
            if text.startswith("```"):
                parts = text.split("```")
                text = next((p.strip() for p in parts if p.strip().startswith("{")), text)
            plan_response = json.loads(text)
        except Exception as e:
            logger.warning("[plan_builder] LLM parse failed: %s", e)
            # Fallback: create a simple plan from selected capabilities
            plan_response = {
                "steps": [
                    {
                        "capability_id": c.get("id"),
                        "title": c.get("title") or c.get("name") or c.get("id"),
                        "description": c.get("description", ""),
                        "inputs": {},
                        "order": i + 1,
                    }
                    for i, c in enumerate(candidate_caps)
                ],
                "confidence": 0.5,
                "plan_summary": "Plan assembled from selected capabilities",
            }

        # Add step IDs — LLM-generated prefills go into run_inputs (ADR-009); inputs stays empty
        steps = []
        for step in plan_response.get("steps") or []:
            steps.append({
                "step_id": f"step-{uuid4().hex[:8]}",
                "capability_id": step.get("capability_id"),
                "title": step.get("title", ""),
                "description": step.get("description", ""),
                "inputs": {},
                "run_inputs": step.get("inputs") or {},
                "order": step.get("order", len(steps) + 1),
                "enabled": True,
            })

        confidence = float(plan_response.get("confidence", 0.5))
        plan_summary = plan_response.get("plan_summary", "")

        logger.info("[plan_builder] built %d steps confidence=%.2f", len(steps), confidence)

        needs_clarification = confidence < 0.65
        clarification_q = None
        if needs_clarification:
            clarification_q = f"I've assembled a plan but I'm not very confident (score={confidence:.0%}). Could you confirm or clarify the details?"
            # Preserve the existing plan if available so the canvas doesn't go blank
            if existing_plan and not steps:
                steps = existing_plan  # type: ignore[assignment]

        return {
            "draft_plan": steps,
            "confidence_score": confidence,
            "needs_clarification": needs_clarification,
            "clarification_question": clarification_q,
            "response_message": f"Plan assembled: {plan_summary}\n{len(steps)} step(s) ready.",
        }

    return _node
