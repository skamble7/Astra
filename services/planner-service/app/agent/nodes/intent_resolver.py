# services/planner-service/app/agent/nodes/intent_resolver.py
from __future__ import annotations

import json
import logging
from typing import Any, Dict

from conductor_core.llm.base import AgentLLM

logger = logging.getLogger("app.agent.nodes.intent_resolver")

_SYSTEM_PROMPT = """You are the intent analysis component of ASTRA, a general-purpose capability orchestration platform.

ASTRA allows users to register and execute *capabilities* — discrete execution units that can do anything: parse COBOL, discover microservices architecture, modernize legacy code, generate API documentation, run security scans, analyse user stories, and more. A capability has a unique id, takes structured inputs, and produces typed artifact outputs.

The *planner* (your parent system) helps users assemble an ordered pipeline of capabilities to solve a goal. Through conversation, the user can:
- Request a new plan from scratch ("discover the architecture of my application")
- Modify an existing plan ("remove the last step", "add a step for API docs", "move step 3 before step 1")
- Ask about what capabilities exist or what a capability does

Your job is to classify the user's latest message and extract structured intent.

IMPORTANT: If a plan already exists in the conversation and the user is asking to change it (add/remove/reorder/replace steps, adjust the pipeline), use intent_type "modify_plan".

Respond ONLY with a single JSON object (no markdown, no explanation):
{
  "intent_type": "discover|generate|document|review|refactor|test|modify_plan|other",
  "description": "concise description of what the user wants",
  "entities": {"files": [], "languages": [], "frameworks": [], "other": []},
  "constraints": [],
  "confidence": 0.0
}

intent_type values:
- discover: user wants to explore, analyse, or understand something (architecture, codebase, data model, etc.)
- generate: user wants to produce new artifacts (code, diagrams, specs, reports)
- document: user wants documentation produced
- review: user wants a review or audit of something
- refactor: user wants code or system changes
- test: user wants tests generated or run
- modify_plan: user wants to change an already-assembled ASTRA capability plan (add/remove/reorder/replace steps)
- other: anything that doesn't fit the above"""


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
