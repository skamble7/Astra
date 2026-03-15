from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from polyllm import LLMClient

from conductor_core.llm.base import AgentLLM, CompletionResult

logger = logging.getLogger("conductor_core.llm.polyllm_agent")


class PolyllmAgentLLM:
    """
    Agent LLM adapter backed by polyllm's LLMClient.
    Implements the AgentLLM protocol for use in mcp_input_resolver_node.
    """

    def __init__(self, client: LLMClient) -> None:
        self._client = client

    async def acomplete(
        self,
        prompt: str,
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> CompletionResult:
        result = await self._client.chat([
            {"role": "system", "content": "You are the conductor agent."},
            {"role": "user", "content": prompt},
        ])
        text = result.text
        logger.debug("Agent LLM completion: %s", text[:200])
        return CompletionResult(text=text, raw={"text": text})

    async def acomplete_json(
        self,
        prompt: str,
        schema: Dict[str, Any],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> CompletionResult:
        schema_str = json.dumps(schema, indent=2)
        enhanced_prompt = (
            f"{prompt}\n\nRespond with valid JSON matching this schema:\n{schema_str}"
        )
        result = await self._client.chat([
            {"role": "system", "content": "You are the conductor agent. Reply strictly in JSON."},
            {"role": "user", "content": enhanced_prompt},
        ])
        text = result.text or "{}"
        logger.debug("Agent LLM JSON completion: %s", text[:200])
        return CompletionResult(text=text, raw={"text": text})
