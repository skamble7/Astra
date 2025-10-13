from __future__ import annotations
from typing import Dict, Optional, Tuple

from app.llm.execution_base import ExecLLM
from app.llm.execution_openai import OpenAIExecAdapter
from app.llm.execution_http import GenericHTTPExecAdapter
from app.secrets.resolver import SecretResolver, ResolvedAuth

def build_exec_llm(
    *,
    provider: str,
    model: str,
    base_url: Optional[str],
    organization: Optional[str],
    headers: Dict[str, str],
    query_params: Dict[str, str],
    timeout_sec: int,
    auth: ResolvedAuth,
) -> ExecLLM:
    provider = (provider or "").lower()

    # Auth header wiring
    auth_header: Optional[str] = None
    basic_tuple: Optional[Tuple[str, str]] = None
    api_key_header: Optional[Tuple[str, str]] = None

    if auth.method == "bearer" and auth.token:
        auth_header = f"Bearer {auth.token}"
    elif auth.method == "basic" and auth.user and auth.password:
        basic_tuple = (auth.user, auth.password)
    elif auth.method == "api_key" and auth.key:
        # NOTE: For generic_http/OpenRouter/etc., pass API key as "Authorization: Bearer" or provider-specific header.
        # Leave it general here; callers can set a static header name in headers if desired.
        # If caller didn’t, we’ll default to "x-api-key".
        if "Authorization" not in headers:
            api_key_header = ("x-api-key", auth.key)

    # Known providers
    if provider in {"openai", "azure_openai"}:
        # The OpenAI SDK also works for Azure if base_url points to your Azure endpoint.
        # Organization is ignored by Azure.
        return OpenAIExecAdapter(
            api_key=auth.token or auth.key,  # bearer or api_key
            base_url=base_url,
            organization=organization if provider == "openai" else None,
            model=model,
            timeout_sec=timeout_sec,
            headers=headers,
            query_params=query_params,
        )

    # Generic HTTP (OpenRouter, custom proxies, Ollama via HTTP, etc.)
    return GenericHTTPExecAdapter(
        base_url=base_url or "",
        headers=headers,
        timeout_sec=timeout_sec,
        query_params=query_params,
        auth_header=auth_header,
        basic_tuple=basic_tuple,
        api_key_header=api_key_header,
    )