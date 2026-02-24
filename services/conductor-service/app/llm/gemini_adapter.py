# services/conductor-service/app/llm/gemini_adapter.py
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from google import genai
from google.genai import types

from app.config import settings
from app.llm.base import AgentLLM, CompletionResult

logger = logging.getLogger("app.llm.gemini")


class GeminiAdapter(AgentLLM):
    """
    Gemini adapter for the conductor agent.
    Uses Google's genai SDK for async completions.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        api_key: Optional[str] = None,
    ) -> None:
        """
        Initialize Gemini adapter with optional config overrides.
        Falls back to settings for any None values.
        """
        resolved_api_key = api_key or settings.llm_api_key
        if not resolved_api_key:
            raise RuntimeError("LLM_API_KEY is not configured")

        self.client = genai.Client(api_key=resolved_api_key)
        self.model = model or settings.llm_model
        self.temperature = temperature if temperature is not None else settings.llm_temperature
        self.max_tokens = max_tokens or settings.llm_max_tokens

    async def acomplete(
        self, prompt: str, *, temperature: Optional[float] = None, max_tokens: Optional[int] = None
    ) -> CompletionResult:
        """
        Free-form text completion.
        """
        config = types.GenerateContentConfig(
            temperature=temperature or self.temperature,
            max_output_tokens=max_tokens or self.max_tokens,
        )

        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=config
        )

        text = response.text or ""
        logger.debug("Gemini completion result: %s", text[:200])
        
        # Convert response to dict for raw storage
        raw_dict = {
            "text": text,
            "model": self.model,
            "usage_metadata": {
                "prompt_token_count": getattr(response.usage_metadata, "prompt_token_count", 0),
                "candidates_token_count": getattr(response.usage_metadata, "candidates_token_count", 0),
                "total_token_count": getattr(response.usage_metadata, "total_token_count", 0),
            } if hasattr(response, "usage_metadata") else {}
        }
        
        return CompletionResult(text=text, raw=raw_dict)

    async def acomplete_json(
        self, prompt: str, schema: Dict[str, Any], *, temperature: Optional[float] = None, max_tokens: Optional[int] = None
    ) -> CompletionResult:
        """
        JSON-constrained completion using response_mime_type.
        Gemini supports JSON mode natively.
        """
        config = types.GenerateContentConfig(
            temperature=temperature or self.temperature,
            max_output_tokens=max_tokens or self.max_tokens,
            response_mime_type="application/json",
        )

        # Enhance prompt with schema guidance
        schema_str = json.dumps(schema, indent=2)
        enhanced_prompt = f"{prompt}\n\nRespond with valid JSON matching this schema:\n{schema_str}"

        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=enhanced_prompt,
            config=config
        )

        text = response.text or "{}"
        logger.debug("Gemini JSON completion result: %s", text[:200])
        
        # Convert response to dict for raw storage
        raw_dict = {
            "text": text,
            "model": self.model,
            "usage_metadata": {
                "prompt_token_count": getattr(response.usage_metadata, "prompt_token_count", 0),
                "candidates_token_count": getattr(response.usage_metadata, "candidates_token_count", 0),
                "total_token_count": getattr(response.usage_metadata, "total_token_count", 0),
            } if hasattr(response, "usage_metadata") else {}
        }
        
        return CompletionResult(text=text, raw=raw_dict)
