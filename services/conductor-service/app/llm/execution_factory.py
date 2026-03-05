from __future__ import annotations

import logging
from typing import Dict, Optional

from polyllm import LLMClient, PolyllmConfig

from app.llm.execution_base import ExecLLM
from app.llm.polyllm_exec import PolyllmExecLLM

logger = logging.getLogger("app.llm.execution_factory")

# Mapping from conductor/capability provider names to polyllm provider identifiers
POLYLLM_PROVIDER_MAP: Dict[str, str] = {
    "openai": "openai",
    "azure_openai": "azure_openai",
    "azure-openai": "azure_openai",
    "gemini": "google_genai",
    "google_genai": "google_genai",
    "anthropic": "anthropic",
    "bedrock": "bedrock",
}

# Provider → env var for API key (used to resolve PROVIDER_API_KEY magic token)
PROVIDER_KEY_MAP: Dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "azure_openai": "AZURE_OPENAI_API_KEY",
    "azure-openai": "AZURE_OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "google_genai": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "cohere": "COHERE_API_KEY",
    "bedrock": "AWS_ACCESS_KEY_ID",
    "openrouter": "OPENROUTER_API_KEY",
}


def _resolve_api_key_ref(auth_config: Optional[dict], provider: str) -> Optional[str]:
    """
    Map a capability's raw auth config dict to a polyllm api_key_ref string.

    Supported auth methods:
      - api_key: uses alias_key (or PROVIDER_API_KEY magic token)
      - bearer:  uses alias_token (or PROVIDER_API_KEY magic token)
      - none / missing: returns None (no auth)
    """
    if not auth_config:
        return None

    method = (auth_config.get("method") or "none").lower()
    if method == "none":
        return None

    alias_key = auth_config.get("alias_key") or auth_config.get("alias_token")

    if alias_key == "PROVIDER_API_KEY":
        # Magic token: map to the provider's canonical env var
        env_var = PROVIDER_KEY_MAP.get(provider.lower())
        if not env_var:
            raise ValueError(
                f"Unknown provider '{provider}' for PROVIDER_API_KEY magic token"
            )
        logger.info(
            "Magic token: PROVIDER_API_KEY + provider=%s → env:%s", provider, env_var
        )
        return f"env:{env_var}"

    if alias_key:
        return f"env:{alias_key}"

    return None


def build_exec_llm(
    *,
    provider: str,
    model: str,
    base_url: Optional[str],
    headers: Dict[str, str],
    query_params: Dict[str, str],
    timeout_sec: int,
    auth_config: Optional[dict],
    temperature: Optional[float],
    top_p: Optional[float],
    max_tokens: Optional[int],
) -> ExecLLM:
    """
    Build an execution LLM adapter backed by polyllm.

    Provider selection, model, temperature/max_tokens, and auth are all
    resolved here and baked into the polyllm profile. The returned adapter
    implements ExecLLM.acomplete().

    Note: top_p is accepted for interface compatibility but is not forwarded —
    polyllm ModelProfile does not have a top_p field.
    """
    _ = top_p  # not in polyllm ModelProfile
    provider_lower = (provider or "").lower()
    polyllm_provider = POLYLLM_PROVIDER_MAP.get(provider_lower, "openai")

    api_key_ref = _resolve_api_key_ref(auth_config, provider_lower)

    profile: dict = {
        "provider": polyllm_provider,
        "model": model,
        "headers": headers or {},
        "query_params": query_params or {},
        "timeout_seconds": timeout_sec,
    }
    if temperature is not None:
        profile["temperature"] = temperature
    if max_tokens is not None:
        profile["max_tokens"] = max_tokens
    if api_key_ref:
        profile["api_key_ref"] = api_key_ref
    if base_url:
        profile["base_url"] = base_url

    cfg = PolyllmConfig(
        default_profile="exec",
        profiles={"exec": profile},
    )
    client = LLMClient(cfg)
    logger.info("Exec LLM ready: provider=%s model=%s", polyllm_provider, model)
    return PolyllmExecLLM(client)
