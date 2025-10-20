from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Optional, Tuple

from app.config import settings

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
    """
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

    def resolve_auth(self, auth_alias: Optional[dict]) -> ResolvedAuth:
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
            key = self.resolve(auth_alias.get("alias_key"))
            if not key:
                raise RuntimeError("Auth resolution failed: alias_key not found")
            return ResolvedAuth(method="api_key", key=key)

        raise ValueError(f"Unsupported auth method: {method}")