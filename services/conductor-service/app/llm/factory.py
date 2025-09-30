# services/conductor-service/app/llm/factory.py
from __future__ import annotations

from app.config import settings
from app.llm.base import AgentLLM
from app.llm.openai_adapter import OpenAIAdapter


def get_agent_llm() -> AgentLLM:
    """
    Factory for the LLM driving the conductor agent.
    Switchable via LLM_PROVIDER in config.
    """
    provider = settings.llm_provider.lower()
    if provider == "openai":
        return OpenAIAdapter()
    # elif provider == "anthropic":
    #     return AnthropicAdapter()
    # elif provider == "ollama":
    #     return OllamaAdapter()
    raise ValueError(f"Unsupported LLM provider: {provider}")