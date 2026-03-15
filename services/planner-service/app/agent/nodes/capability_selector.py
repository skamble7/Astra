# services/planner-service/app/agent/nodes/capability_selector.py
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from conductor_core.llm.base import AgentLLM
from app.cache.manifest_cache import ManifestCache

logger = logging.getLogger("app.agent.nodes.capability_selector")

_SYSTEM_PROMPT = """You are a capability matching system for a software development assistant.
Given a user intent, select the most relevant capabilities from the available list.

Respond ONLY with a single JSON object:
{
  "selected": [
    {"id": "cap.xxx", "confidence": 0.9, "reason": "brief reason", "order": 1}
  ],
  "needs_clarification": false,
  "clarification_question": null
}

Order the selected capabilities by execution order (dependencies first).
Only include capabilities that are directly needed to fulfill the intent.
"""


def capability_selector_node(*, llm: AgentLLM, cache: ManifestCache):
    async def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        intent = state.get("intent") or {}
        error = state.get("error")

        if error:
            return {}

        # Fetch all capabilities
        try:
            all_caps = await cache.get_all_capabilities()
        except Exception as e:
            logger.warning("[capability_selector] cache fetch failed: %s", e)
            all_caps = []

        if not all_caps:
            return {
                "candidate_capabilities": [],
                "needs_clarification": True,
                "clarification_question": "I couldn't load the available capabilities. Please try again.",
            }

        # Build compact capability summary for LLM
        caps_summary = []
        for cap in all_caps:
            caps_summary.append({
                "id": cap.get("id"),
                "title": cap.get("title") or cap.get("name"),
                "description": cap.get("description", ""),
                "produces_kinds": cap.get("produces_kinds", []),
                "mode": (cap.get("execution") or {}).get("mode", "mcp"),
            })

        prompt = (
            f"{_SYSTEM_PROMPT}\n\n"
            f"Available capabilities:\n{json.dumps(caps_summary, indent=2)}\n\n"
            f"User intent:\n{json.dumps(intent, indent=2)}\n\n"
            "Select the capabilities needed to fulfill this intent."
        )

        try:
            result = await llm.acomplete(prompt)
            text = (result.text or "").strip()
            if text.startswith("```"):
                parts = text.split("```")
                text = next((p.strip() for p in parts if p.strip().startswith("{")), text)
            selection = json.loads(text)
        except Exception as e:
            logger.warning("[capability_selector] LLM parse failed: %s", e)
            selection = {"selected": [], "needs_clarification": True,
                         "clarification_question": "I'm having trouble understanding the request. Could you clarify?"}

        # Resolve full capability objects for selected IDs
        selected_ids = {s.get("id") for s in (selection.get("selected") or [])}
        caps_by_id = {c.get("id"): c for c in all_caps}
        candidate_caps = []
        for sel in sorted(selection.get("selected") or [], key=lambda x: x.get("order", 99)):
            cap_id = sel.get("id")
            cap = caps_by_id.get(cap_id)
            if cap:
                candidate_caps.append({**cap, "_selector_confidence": sel.get("confidence", 0.5), "_selector_reason": sel.get("reason", "")})

        logger.info("[capability_selector] selected %d capabilities", len(candidate_caps))
        return {
            "candidate_capabilities": candidate_caps,
            "needs_clarification": selection.get("needs_clarification", False),
            "clarification_question": selection.get("clarification_question"),
        }

    return _node
