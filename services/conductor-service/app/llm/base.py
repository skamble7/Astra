# services/conductor-service/app/llm/base.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol


@dataclass
class CompletionResult:
    text: str
    raw: Dict[str, Any]


class AgentLLM(Protocol):
    """
    Interface for the LLM that drives the conductor agent.
    """

    async def acomplete(
        self, prompt: str, *, temperature: Optional[float] = None, max_tokens: Optional[int] = None
    ) -> CompletionResult:
        """
        Free-form completion. Return text only.
        """

    async def acomplete_json(
        self, prompt: str, schema: Dict[str, Any], *, temperature: Optional[float] = None, max_tokens: Optional[int] = None
    ) -> CompletionResult:
        """
        Completion constrained to strict JSON schema.
        """