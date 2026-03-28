# services/workspace-manager-service/app/clients/registry_client.py
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger("app.clients.registry")


class RegistryClient:
    """
    Thin async HTTP client for artifact-service registry endpoints.
    Used by workspace-manager-service to delegate schema validation/envelope
    building to artifact-service rather than duplicating registry logic.
    """

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    async def build_envelope(
        self,
        *,
        kind: str,
        name: str,
        data: Dict[str, Any],
        schema_version: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        POST /registry/build-envelope
        Returns the validated, migrated, adapted envelope with natural_key, fingerprint, etc.
        Raises httpx.HTTPStatusError on failure.
        """
        payload: Dict[str, Any] = {"kind": kind, "name": name, "data": data}
        if schema_version is not None:
            payload["schema_version"] = schema_version

        async with httpx.AsyncClient(base_url=self._base_url, timeout=30.0) as client:
            resp = await client.post("/registry/build-envelope", json=payload)
            resp.raise_for_status()
            return resp.json()

    async def get_kind(self, kind_id: str) -> Optional[Dict[str, Any]]:
        """
        GET /registry/kinds/{kind_id}
        Returns None on 404.
        """
        async with httpx.AsyncClient(base_url=self._base_url, timeout=10.0) as client:
            resp = await client.get(f"/registry/kinds/{kind_id}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
