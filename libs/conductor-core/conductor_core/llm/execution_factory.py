from __future__ import annotations

import logging

from polyllm import RemoteConfigLoader

from conductor_core.llm.execution_base import ExecLLM
from conductor_core.llm.polyllm_exec import PolyllmExecLLM

logger = logging.getLogger("conductor_core.llm.execution_factory")


async def build_exec_llm_from_ref(llm_config_ref: str) -> ExecLLM:
    """
    Build an execution LLM adapter by fetching the profile from ConfigForge.

    CONFIG_FORGE_URL must be set in the environment.

    Args:
        llm_config_ref: ConfigForge canonical ref, e.g. "dev.llm.openai.fast".

    Returns:
        An ExecLLM adapter backed by the resolved polyllm LLMClient.
    """
    loader = RemoteConfigLoader()  # reads CONFIG_FORGE_URL from environment
    client = await loader.load(llm_config_ref)
    logger.info("Exec LLM ready via ConfigForge: ref=%s", llm_config_ref)
    return PolyllmExecLLM(client)
