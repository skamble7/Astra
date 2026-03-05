from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from polyllm import LLMClient, PolyllmConfig

from app.config import settings
from app.llm.base import AgentLLM
from app.llm.polyllm_agent import PolyllmAgentLLM

logger = logging.getLogger("app.llm.factory")

# Mapping from conductor provider names to polyllm provider identifiers
POLYLLM_PROVIDER_MAP: Dict[str, str] = {
    "openai": "openai",
    "gemini": "google_genai",
    "google_genai": "google_genai",
    "anthropic": "anthropic",
    "bedrock": "bedrock",
    "azure_openai": "azure_openai",
    "azure-openai": "azure_openai",
}

# Mapping from provider to the env var holding its API key
PROVIDER_KEY_MAP: Dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "google_genai": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "cohere": "COHERE_API_KEY",
    "azure_openai": "AZURE_OPENAI_API_KEY",
    "azure-openai": "AZURE_OPENAI_API_KEY",
}


def get_agent_llm(llm_config: Optional[Dict[str, Any]] = None) -> AgentLLM:
    """
    Factory for the LLM driving the conductor agent, backed by polyllm.

    Args:
        llm_config: Optional configuration override from StartRunRequest.llm_config.
                    Falls back to settings.* for any None/missing fields.
    """
    if llm_config is None:
        llm_config = {}

    provider = llm_config.get("provider") or settings.llm_provider
    model = llm_config.get("model") or settings.llm_model

    temperature = llm_config.get("temperature")
    if temperature is None:
        temperature = settings.llm_temperature

    max_tokens = llm_config.get("max_tokens") or settings.llm_max_tokens

    provider_lower = provider.lower()
    polyllm_provider = POLYLLM_PROVIDER_MAP.get(provider_lower, provider_lower)

    # Resolve which env var holds the API key.
    # If using the conductor's default provider, use LLM_API_KEY.
    # If overriding to a different provider, use that provider's canonical key.
    if provider_lower == settings.llm_provider.lower():
        api_key_ref = "env:LLM_API_KEY"
    else:
        env_var = PROVIDER_KEY_MAP.get(provider_lower, "LLM_API_KEY")
        api_key_ref = f"env:{env_var}"

    cfg = PolyllmConfig(
        default_profile="agent",
        profiles={
            "agent": {
                "provider": polyllm_provider,
                "model": model,
                "api_key_ref": api_key_ref,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        },
    )
    client = LLMClient(cfg)
    logger.info("Agent LLM ready: provider=%s model=%s", polyllm_provider, model)
    return PolyllmAgentLLM(client)
