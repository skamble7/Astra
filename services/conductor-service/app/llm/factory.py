# services/conductor-service/app/llm/factory.py
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from app.config import settings
from app.llm.base import AgentLLM
from app.llm.openai_adapter import OpenAIAdapter
from app.llm.gemini_adapter import GeminiAdapter


# Provider-to-environment-variable mapping (same pattern as SecretResolver)
PROVIDER_KEY_MAP = {
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "cohere": "COHERE_API_KEY",
    "azure-openai": "AZURE_OPENAI_API_KEY",
}


def get_agent_llm(llm_config: Optional[Dict[str, Any]] = None) -> AgentLLM:
    """
    Factory for the LLM driving the conductor agent.
    
    Args:
        llm_config: Optional configuration override from StartRunRequest.llm_config
                   Falls back to settings.* for any None/missing fields
    
    Returns:
        Configured AgentLLM adapter (OpenAI, Gemini, etc.)
    
    Raises:
        ValueError: If provider is not supported
    """
    if llm_config is None:
        llm_config = {}
    
    # Merge with fallback to settings
    provider = llm_config.get("provider") or settings.llm_provider
    model = llm_config.get("model") or settings.llm_model
    
    temperature = llm_config.get("temperature")
    if temperature is None:
        temperature = settings.llm_temperature
    
    max_tokens = llm_config.get("max_tokens")
    if max_tokens is None:
        max_tokens = settings.llm_max_tokens
    
    strict_json = llm_config.get("strict_json")
    if strict_json is None:
        strict_json = settings.llm_strict_json
    
    # Resolve provider-specific API key
    # If provider differs from settings.llm_provider, use provider-specific env var
    # Otherwise, use LLM_API_KEY (conductor's default)
    provider_lower = provider.lower()
    
    if provider_lower == settings.llm_provider.lower():
        # Using conductor's default provider, use LLM_API_KEY
        api_key = settings.llm_api_key
    else:
        # Using different provider, resolve to provider-specific key
        env_var_name = PROVIDER_KEY_MAP.get(provider_lower)
        if env_var_name:
            api_key = os.getenv(env_var_name)
            if not api_key:
                raise ValueError(
                    f"Provider '{provider}' requires {env_var_name} environment variable to be set"
                )
        else:
            # Fallback to LLM_API_KEY for unknown providers
            api_key = settings.llm_api_key
    
    # Build adapter with merged config
    if provider_lower == "openai":
        return OpenAIAdapter(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            strict_json=strict_json,
            api_key=api_key,
        )
    elif provider_lower == "gemini":
        return GeminiAdapter(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=api_key,
        )
    # elif provider_lower == "anthropic":
    #     return AnthropicAdapter(
    #         model=model,
    #         temperature=temperature,
    #         max_tokens=max_tokens,
    #     )
    
    raise ValueError(f"Unsupported LLM provider: {provider}")