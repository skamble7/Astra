# services/conductor-service/app/llm/execution_base.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol


@dataclass
class ExecResult:
    """
    Generic return object for an LLM execution.
    - text:  the main text output (trimmed string)
    - raw:   the full provider response (already JSON-serializable)
    """
    text: str
    raw: Dict[str, Any]


class ExecLLM(Protocol):
    """
    Unified async interface for all provider adapters used by llm_execution_node.
    Each adapter (OpenAIExecAdapter, GenericHTTPExecAdapter, etc.) implements
    this protocol.
    """

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
        Implementations must return an ExecResult.
        """