from __future__ import annotations
import os
import logging
from dataclasses import dataclass
from typing import Optional, Tuple

from app.config import settings

logger = logging.getLogger("app.secrets.resolver")

@dataclass
class ResolvedAuth:
    method: str  # "none" | "bearer" | "basic" | "api_key"
    token: Optional[str] = None
    user: Optional[str] = None
    password: Optional[str] = None
    key: Optional[str] = None

class SecretResolver:
    """
    Pluggable secret resolver. Today: env. Tomorrow: Vault/KMS/etc.
    
    Supports Magic Token: PROVIDER_API_KEY automatically resolves based on provider field.
    """
    
    # Provider → environment variable name mapping
    PROVIDER_KEY_MAP = {
        "openai": "OPENAI_API_KEY",
        "azure_openai": "AZURE_OPENAI_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "cohere": "COHERE_API_KEY",
        "bedrock": "AWS_ACCESS_KEY_ID",
        "openrouter": "OPENROUTER_API_KEY",
    }
    
    def resolve_env(self, alias: str) -> Optional[str]:
        if not alias:
            return None
        # 1) Direct env hit
        v = os.getenv(alias)
        if v:
            return v
        # 2) Namespaced alias (e.g., ASTRA_SECRET_OPENAI)
        namespaced = f"{settings.secret_alias_prefix}{alias}".upper()
        return os.getenv(namespaced)

    def resolve(self, alias: Optional[str]) -> Optional[str]:
        if not alias:
            return None
        backend = settings.secret_backend.lower()
        if backend == "env":
            return self.resolve_env(alias)
        # future: vault/kms/ssm/etc.
        raise ValueError(f"Unsupported secret backend: {backend}")

    def resolve_auth(self, auth_alias: Optional[dict], provider: Optional[str] = None) -> ResolvedAuth:
        """
        Resolve auth based on capability config + provider context.
        
        Priority for alias_key resolution:
        1. Magic token "PROVIDER_API_KEY" → map using provider parameter
        2. Explicit alias_key value (direct lookup)
        3. No alias_key but provider specified → convention-based (future)
        
        Args:
            auth_alias: Auth config dict from capability
            provider: Provider name (openai, gemini, etc.) for magic token resolution
        """
        if not auth_alias:
            return ResolvedAuth(method="none")

        method = (auth_alias.get("method") or "none").lower()
        if method == "none":
            return ResolvedAuth(method="none")

        if method == "bearer":
            token = self.resolve(auth_alias.get("alias_token"))
            if not token:
                raise RuntimeError("Auth resolution failed: alias_token not found")
            return ResolvedAuth(method="bearer", token=token)

        if method == "basic":
            user = self.resolve(auth_alias.get("alias_user"))
            password = self.resolve(auth_alias.get("alias_password"))
            if not user or not password:
                raise RuntimeError("Auth resolution failed: alias_user/alias_password not found")
            return ResolvedAuth(method="basic", user=user, password=password)

        if method == "api_key":
            alias_key = auth_alias.get("alias_key")
            
            # Magic token: PROVIDER_API_KEY → resolve based on provider
            if alias_key == "PROVIDER_API_KEY":
                if not provider:
                    raise RuntimeError("Magic token PROVIDER_API_KEY used but no provider specified")
                
                provider_lower = provider.lower()
                mapped_key = self.PROVIDER_KEY_MAP.get(provider_lower)
                
                if not mapped_key:
                    raise RuntimeError(f"Unknown provider '{provider}' for magic token PROVIDER_API_KEY")
                
                logger.info(f"Magic token: PROVIDER_API_KEY + provider={provider} → {mapped_key}")
                alias_key = mapped_key
            
            # Resolve the final key from environment
            key = self.resolve(alias_key)
            if not key:
                raise RuntimeError(f"Auth resolution failed: alias_key '{alias_key}' not found")
            return ResolvedAuth(method="api_key", key=key)

        raise ValueError(f"Unsupported auth method: {method}")