# services/planner-service/app/agent/nodes/intent_resolver.py
from __future__ import annotations

import json
import logging
from typing import Any, Dict

from conductor_core.llm.base import AgentLLM

logger = logging.getLogger("app.agent.nodes.intent_resolver")

_SYSTEM_PROMPT = """You are an intent analysis system for a software development assistant.
Analyze user messages and extract structured intent.

Respond ONLY with a single JSON object (no markdown, no explanation):
{
  "intent_type": "analyze|generate|document|review|refactor|test|other",
  "description": "concise description of what the user wants",
  "entities": {"files": [], "languages": [], "frameworks": [], "other": []},
  "constraints": [],
  "confidence": 0.0
}"""


def intent_resolver_node(*, llm: AgentLLM):
    async def _node(state: Dict[str, Any]) -> Dict[str, Any]:
        message = state.get("current_message", "")
        messages = state.get("messages", [])
        error = state.get("error")

        if error:
            return {}  # propagate failure

        # Build context from recent history (last 6 messages)
        history_parts = []
        for m in messages[-6:]:
            role = m.get("role", "user")
            content = m.get("content", "")
            history_parts.append(f"{role}: {content}")
        context = "\n".join(history_parts)

        prompt = f"{_SYSTEM_PROMPT}\n\nConversation context:\n{context}\n\nLatest user message: {message}\n\nExtract the intent."

        try:
            result = await llm.acomplete(prompt)
            text = (result.text or "").strip()
            # Strip markdown fences if present
            if text.startswith("```"):
                parts = text.split("```")
                text = next((p.strip() for p in parts if p.strip().startswith("{")), text)
            intent = json.loads(text)
            logger.info("[intent_resolver] intent_type=%s confidence=%.2f", intent.get("intent_type"), intent.get("confidence", 0))
            return {"intent": intent}
        except Exception as e:
            logger.warning("[intent_resolver] parse failed: %s", e)
            # Fallback intent
            return {
                "intent": {
                    "intent_type": "other",
                    "description": message,
                    "entities": {},
                    "constraints": [],
                    "confidence": 0.5,
                }
            }

    return _node
