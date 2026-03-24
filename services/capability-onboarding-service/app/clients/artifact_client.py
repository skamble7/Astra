from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from app.config import settings

logger = logging.getLogger("app.clients.artifact")


class ArtifactServiceClient:
    """Thin async HTTP client for the artifact-service registry endpoints."""

    def __init__(self) -> None:
        self._base = settings.artifact_svc_base_url
        self._timeout = settings.http_client_timeout_seconds

    async def kind_exists(self, kind_id: str) -> bool:
        """Returns True if the artifact kind is already registered."""
        async with httpx.AsyncClient(base_url=self._base, timeout=self._timeout) as client:
            resp = await client.get(f"/registry/kinds/{kind_id}")
            return resp.status_code == 200

    async def create_kind(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Creates a new artifact kind. Returns the created doc, or None if it
        already exists (409 is absorbed silently).
        Raises for other HTTP errors.
        """
        async with httpx.AsyncClient(base_url=self._base, timeout=self._timeout) as client:
            resp = await client.post("/registry/kinds", json=payload)
            if resp.status_code == 409:
                logger.info("[artifact-service] Kind already exists (409 absorbed): %s", payload.get("_id"))
                return None
            _raise_for_status("artifact-service", resp)
            return resp.json()


def _raise_for_status(service: str, resp: httpx.Response) -> None:
    if resp.is_success:
        return
    body = resp.text[:500] if resp.text else ""
    logger.error("[%s] HTTP %s: %s", service, resp.status_code, body)
    resp.raise_for_status()
