# services/planner-service/app/clients/capability_service.py
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings

logger = logging.getLogger("app.clients.capability_service")


class CapabilityServiceClient:
    """HTTP client for the capability-service (9021)."""

    def __init__(self, base_url: Optional[str] = None) -> None:
        self._base = (base_url or settings.capability_svc_base_url).rstrip("/")
        self._timeout = settings.http_client_timeout_seconds

    async def list_capabilities(self, *, limit: int = 200) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._base}/capability/search",
                params={"limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return data
            return data.get("items") or data.get("capabilities") or []

    async def get_capability(self, cap_id: str) -> Optional[Dict[str, Any]]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{self._base}/capability/{cap_id}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
