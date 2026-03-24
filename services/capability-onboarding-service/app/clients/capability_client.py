from __future__ import annotations

import logging
from typing import Any, Dict

import httpx

from app.config import settings

logger = logging.getLogger("app.clients.capability")


class CapabilityServiceClient:
    """Thin async HTTP client for the capability-service."""

    def __init__(self) -> None:
        self._base = settings.capability_svc_base_url
        self._timeout = settings.http_client_timeout_seconds

    async def create_capability(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with httpx.AsyncClient(base_url=self._base, timeout=self._timeout) as client:
            resp = await client.post("/capability/", json=payload)
            _raise_for_status("capability-service", resp)
            return resp.json()

    async def get_capability(self, capability_id: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(base_url=self._base, timeout=self._timeout) as client:
            resp = await client.get(f"/capability/{capability_id}")
            _raise_for_status("capability-service", resp)
            return resp.json()


def _raise_for_status(service: str, resp: httpx.Response) -> None:
    if resp.is_success:
        return
    body = resp.text[:500] if resp.text else ""
    logger.error("[%s] HTTP %s: %s", service, resp.status_code, body)
    resp.raise_for_status()
