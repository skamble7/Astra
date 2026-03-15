from __future__ import annotations

import logging
import os
from typing import Optional

from polyllm import RemoteConfigLoader

from conductor_core.llm.base import AgentLLM
from conductor_core.llm.polyllm_agent import PolyllmAgentLLM

logger = logging.getLogger("conductor_core.llm.factory")


async def get_agent_llm(llm_config_ref: Optional[str] = None) -> AgentLLM:
    """
    Build the conductor agent LLM via ConfigForge (polyllm RemoteConfigLoader).

    Args:
        llm_config_ref: Per-request override ref. Falls back to
                        CONDUCTOR_LLM_CONFIG_REF env var when not provided.

    Raises:
        ValueError: If no ref is available (neither per-request nor env-configured).
    """
    ref = llm_config_ref or os.getenv("CONDUCTOR_LLM_CONFIG_REF", "")
    if not ref:
        raise ValueError(
            "No LLM config ref available for conductor agent. "
            "Set CONDUCTOR_LLM_CONFIG_REF or pass llm_config_ref in the run request."
        )
    loader = RemoteConfigLoader()  # reads CONFIG_FORGE_URL from environment
    client = await loader.load(ref)
    logger.info("Agent LLM ready via ConfigForge: ref=%s", ref)
    return PolyllmAgentLLM(client)
