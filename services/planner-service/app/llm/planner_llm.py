# services/planner-service/app/llm/planner_llm.py
"""
Factory for the planner agent's LangChain ChatModel.

Loads the ModelProfile from ConfigForge via PLANNER_LLM_CONFIG_REF (same
mechanism polyllm uses) then uses polyllm's provider adapters to instantiate
a LangChain ChatModel that supports bind_tools() for the agentic loop.

This bypasses polyllm's LLMClient wrapper (which doesn't expose the model)
while reusing all of polyllm's credential-resolution and per-provider
model-construction logic.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger("app.llm.planner_llm")


async def get_planner_chat_model() -> Any:
    """
    Load the ModelProfile from ConfigForge and return a LangChain ChatModel
    with tool-calling support.

    Reads:
      PLANNER_LLM_CONFIG_REF — ConfigForge canonical ref (e.g. dev.llm.openai.fast)
      CONFIG_FORGE_URL        — ConfigForge base URL

    Raises:
      ValueError if PLANNER_LLM_CONFIG_REF is not set.
    """
    ref = os.getenv("PLANNER_LLM_CONFIG_REF", "")
    if not ref:
        raise ValueError(
            "PLANNER_LLM_CONFIG_REF is not set. "
            "Add it to your .env file (e.g. PLANNER_LLM_CONFIG_REF=dev.llm.openai.fast)."
        )

    # Load ModelProfile from ConfigForge
    from polyllm import RemoteConfigLoader
    from polyllm.providers import get_provider_adapter

    loader = RemoteConfigLoader()  # reads CONFIG_FORGE_URL from env
    client = await loader.load(ref)

    # Access the resolved profile and secrets from the LLMClient
    profile = client.cfg.profiles.get("default") or next(iter(client.cfg.profiles.values()))
    secrets = client.secrets

    # Resolve API key (api_key_ref → env var lookup, literal, etc.)
    api_key: Optional[str] = None
    if profile.api_key_ref:
        api_key = secrets.get(profile.api_key_ref)
    elif profile.api_key_env:
        api_key = secrets.get(f"env:{profile.api_key_env}")

    # Resolve multi-credential bundle (e.g. Bedrock access_key / secret_key)
    credentials = {}
    for name, cred_ref in (profile.secret_refs or {}).items():
        if cred_ref:
            val = secrets.get(cred_ref)
            if val is None:
                raise ValueError(
                    f"Missing secret '{name}' (ref='{cred_ref}') for profile "
                    f"{profile.provider}:{profile.model}"
                )
            credentials[name] = val

    # Delegate to polyllm's provider adapter — same logic as LLMClient.chat()
    adapter = get_provider_adapter(profile.provider)
    model = adapter.create_chat_model(
        profile,
        api_key=api_key,
        credentials=credentials,
        secrets=secrets,
    )

    logger.info(
        "[planner_llm] model ready: provider=%s model=%s ref=%s",
        profile.provider, profile.model, ref,
    )
    return model
