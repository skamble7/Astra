# services/planner-service/app/clients/artifact_service.py
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from app.config import settings

logger = logging.getLogger("app.clients.artifact_service")


class ArtifactServiceClient:
    """HTTP client for artifact-service (implements ArtifactServiceClientProtocol)."""

    def __init__(self, base_url: Optional[str] = None) -> None:
        self._base = (base_url or settings.artifact_svc_base_url).rstrip("/")
        self._timeout = settings.http_client_timeout_seconds

    async def get_kind(self, kind_id: str, *, correlation_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        headers = {}
        if correlation_id:
            headers["X-Correlation-Id"] = correlation_id
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._base}/registry/kinds/{kind_id}", headers=headers)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()

    async def get_kind_schema(self, kind_id: str, version: str, *, correlation_id: Optional[str] = None) -> Dict[str, Any]:
        headers = {}
        if correlation_id:
            headers["X-Correlation-Id"] = correlation_id
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._base}/registry/kinds/{kind_id}/schema/{version}", headers=headers)
            resp.raise_for_status()
            return resp.json()

