from __future__ import annotations

import logging
from typing import Optional

from polyllm import LLMClient

from conductor_core.llm.execution_base import ExecLLM, ExecResult

logger = logging.getLogger("conductor_core.llm.polyllm_exec")


class PolyllmExecLLM:
    """
    Execution LLM adapter backed by polyllm's LLMClient.
    Implements the ExecLLM protocol for use in llm_execution_node.

    Note: temperature, top_p, and max_tokens are baked into the polyllm profile
    at construction time via the factory. Per-call overrides are not supported
    by polyllm's chat() interface.
    """

    def __init__(self, client: LLMClient) -> None:
        self._client = client

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

        result = await self._client.chat(msgs)
        text = (result.text or "").strip()
        logger.debug("Exec LLM result: %s", text[:200])
        return ExecResult(text=text, raw={"text": text})
