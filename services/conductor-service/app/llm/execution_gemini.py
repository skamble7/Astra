# services/conductor-service/app/llm/execution_gemini.py
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from google import genai
from google.genai import types

from app.llm.execution_base import ExecLLM, ExecResult

logger = logging.getLogger("app.llm.exec.gemini")


class GeminiExecAdapter(ExecLLM):
    """
    Gemini execution adapter for LLM-type capabilities.
    Implements the ExecLLM protocol for playbook capability execution.
    """

    def __init__(
        self,
        *,
        api_key: Optional[str],
        model: str,
        timeout_sec: int,
        headers: Dict[str, str],
        query_params: Dict[str, str],
    ) -> None:
        if not api_key:
            raise RuntimeError("Gemini API key is required")

        self.client = genai.Client(api_key=api_key)
        self.model_name = model
        self.timeout_sec = timeout_sec
        self.headers = headers or {}
        self.query_params = query_params or {}

    async def acomplete(
        self,
        *,
        system_prompt: Optional[str],
        user_prompt: str,
        temperature: Optional[float],
        top_p: Optional[float],
        max_tokens: Optional[int],
    ) -> ExecResult:
        """
        Perform one completion call.
        Gemini doesn't have separate system/user roles, so we combine them.
        """
        # Combine system and user prompts
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{user_prompt}"
        else:
            full_prompt = user_prompt

        config = types.GenerateContentConfig(
            temperature=temperature if temperature is not None else 0.7,
            top_p=top_p if top_p is not None else 0.95,
            max_output_tokens=max_tokens,
        )

        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=full_prompt,
            config=config
        )

        text = (response.text or "").strip()
        logger.debug("Gemini exec result: %s", text[:200])

        # Convert response to dict for raw storage
        raw_dict = {
            "text": text,
            "model": self.model_name,
            "usage_metadata": {
                "prompt_token_count": getattr(response.usage_metadata, "prompt_token_count", 0),
                "candidates_token_count": getattr(response.usage_metadata, "candidates_token_count", 0),
                "total_token_count": getattr(response.usage_metadata, "total_token_count", 0),
            } if hasattr(response, "usage_metadata") else {}
        }

        return ExecResult(text=text, raw=raw_dict)
