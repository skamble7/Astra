# services/planner-service/app/clients/workspace_manager.py
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings

logger = logging.getLogger("app.clients.workspace_manager")


class WorkspaceManagerClient:
    """HTTP client for workspace-manager-service (implements WorkspaceManagerClientProtocol)."""

    def __init__(self, base_url: Optional[str] = None) -> None:
        self._base = (base_url or settings.workspace_mgr_base_url).rstrip("/")
        self._timeout = settings.http_client_timeout_seconds

    async def upsert_batch(self, *, workspace_id: str, items: List[Dict[str, Any]], run_id: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=max(self._timeout, 120.0)) as client:
            resp = await client.post(
                f"{self._base}/artifact/{workspace_id}/upsert-batch",
                headers={"X-Run-Id": run_id},
                json={"items": items},
            )
            resp.raise_for_status()
            return resp.json()
