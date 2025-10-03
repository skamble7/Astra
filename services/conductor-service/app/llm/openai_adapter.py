# services/conductor-service/app/llm/openai_adapter.py
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from openai import AsyncOpenAI

from app.config import settings
from app.llm.base import AgentLLM, CompletionResult

logger = logging.getLogger("app.llm.openai")


class OpenAIAdapter(AgentLLM):
    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.llm_model
        self.temperature = settings.llm_temperature
        self.max_tokens = settings.llm_max_tokens
        self.strict_json = settings.llm_strict_json

    async def acomplete(
        self, prompt: str, *, temperature: Optional[float] = None, max_tokens: Optional[int] = None
    ) -> CompletionResult:
        """
        Free-form text completion.
        """
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": "You are the conductor agent."},
                      {"role": "user", "content": prompt}],
            temperature=temperature or self.temperature,
            max_tokens=max_tokens or self.max_tokens,
        )

        text = resp.choices[0].message.content or ""
        logger.debug("OpenAI completion result: %s", text[:200])
        return CompletionResult(text=text, raw=resp.model_dump())

    async def acomplete_json(
        self, prompt: str, schema: Dict[str, Any], *, temperature: Optional[float] = None, max_tokens: Optional[int] = None
    ) -> CompletionResult:
        """
        JSON-constrained completion using response_format.
        """
        response_format = {"type": "json_schema", "json_schema": schema}

        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": "You are the conductor agent. Reply strictly in JSON."},
                      {"role": "user", "content": prompt}],
            temperature=temperature or self.temperature,
            max_tokens=max_tokens or self.max_tokens,
            response_format=response_format if self.strict_json else None,
        )

        text = resp.choices[0].message.content or "{}"
        logger.debug("OpenAI JSON completion result: %s", text[:200])
        return CompletionResult(text=text, raw=resp.model_dump())