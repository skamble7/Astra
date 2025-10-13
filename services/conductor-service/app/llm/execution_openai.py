from __future__ import annotations
import logging
from typing import Any, Dict, Optional

from openai import AsyncOpenAI
from app.llm.execution_base import ExecLLM, ExecResult

logger = logging.getLogger("app.llm.exec.openai")

class OpenAIExecAdapter(ExecLLM):
    def __init__(
        self,
        *,
        api_key: Optional[str],
        base_url: Optional[str],
        organization: Optional[str],
        model: str,
        timeout_sec: int,
        headers: Dict[str, str],
        query_params: Dict[str, str],
    ) -> None:
        # The OpenAI SDK accepts base_url and organization
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            organization=organization,
            default_headers=headers or None,
            timeout=timeout_sec,
        )
        self.model = model
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
        msgs = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        msgs.append({"role": "user", "content": user_prompt})

        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=msgs,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            **self.query_params,  # allows provider-specific query args (non-secret)
        )
        text = (resp.choices[0].message.content or "").strip()
        return ExecResult(text=text, raw=resp.model_dump())