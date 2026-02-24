# services/conductor-service/app/llm/factory.py
from __future__ import annotations

from typing import Any, Dict, Optional

from app.config import settings
from app.llm.base import AgentLLM
from app.llm.openai_adapter import OpenAIAdapter
from app.llm.gemini_adapter import GeminiAdapter


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
    
    # Build adapter with merged config
    provider_lower = provider.lower()
    
    if provider_lower == "openai":
        return OpenAIAdapter(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            strict_json=strict_json,
        )
    elif provider_lower == "gemini":
        return GeminiAdapter(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    # elif provider_lower == "anthropic":
    #     return AnthropicAdapter(
    #         model=model,
    #         temperature=temperature,
    #         max_tokens=max_tokens,
    #     )
    
    raise ValueError(f"Unsupported LLM provider: {provider}")