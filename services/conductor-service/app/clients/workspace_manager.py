# services/conductor-service/app/clients/workspace_manager.py
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.config import settings
from app.clients.http_utils import get_http_client, _raise_for_status, retryable_get

logger = logging.getLogger("app.clients.workspace_manager")


def _merge_headers(
    *,
    correlation_id: Optional[str] = None,
    extras: Optional[Dict[str, str]] = None,
) -> Optional[Dict[str, str]]:
    headers: Dict[str, str] = {}
    if correlation_id:
        headers["X-Correlation-Id"] = correlation_id
    if extras:
        headers.update({k: v for k, v in extras.items() if v is not None})
    return headers or None


class WorkspaceManagerClient:
    """
    Thin async client for workspace-manager-service.
    Handles all workspace artifact CRUD operations.
    """

    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url = base_url or settings.workspace_mgr_base_url
        self.service_name = "workspace-manager-service"

    async def upsert_artifact(
        self,
        workspace_id: str,
        item: Dict[str, Any],
        *,
        run_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /artifact/{workspace_id}"""
        client = await get_http_client(self.base_url)
        url = f"/artifact/{workspace_id}"
        headers = _merge_headers(
            correlation_id=correlation_id,
            extras={"X-Run-Id": run_id} if run_id else None,
        )
        resp = await client.post(url, json=item, headers=headers)
        _raise_for_status(self.service_name, resp)
        return resp.json()

    async def upsert_batch(
        self,
        workspace_id: str,
        items: List[Dict[str, Any]],
        *,
        run_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /artifact/{workspace_id}/upsert-batch"""
        client = await get_http_client(self.base_url)
        url = f"/artifact/{workspace_id}/upsert-batch"
        headers = _merge_headers(
            correlation_id=correlation_id,
            extras={"X-Run-Id": run_id} if run_id else None,
        )
        resp = await client.post(url, json={"items": items}, headers=headers)
        _raise_for_status(self.service_name, resp)
        return resp.json()

    @retryable_get
    async def get_workspace_parent(
        self,
        workspace_id: str,
        *,
        include_deleted: bool = False,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """GET /artifact/{workspace_id}/parent"""
        client = await get_http_client(self.base_url)
        headers = _merge_headers(correlation_id=correlation_id)
        resp = await client.get(
            f"/artifact/{workspace_id}/parent",
            params={"include_deleted": str(include_deleted).lower()},
            headers=headers,
        )
        _raise_for_status(self.service_name, resp)
        return resp.json()

    @retryable_get
    async def list_artifacts(
        self,
        workspace_id: str,
        *,
        kind: Optional[str] = None,
        name_prefix: Optional[str] = None,
        include_deleted: bool = False,
        limit: int = 50,
        offset: int = 0,
        correlation_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """GET /artifact/{workspace_id}"""
        client = await get_http_client(self.base_url)
        params: Dict[str, Any] = {
            "include_deleted": str(include_deleted).lower(),
            "limit": limit,
            "offset": offset,
        }
        if kind:
            params["kind"] = kind
        if name_prefix:
            params["name_prefix"] = name_prefix
        headers = _merge_headers(correlation_id=correlation_id)
        resp = await client.get(f"/artifact/{workspace_id}", params=params, headers=headers)
        _raise_for_status(self.service_name, resp)
        return resp.json()

    @retryable_get
    async def compute_deltas(
        self,
        workspace_id: str,
        *,
        run_id: str,
        include_ids: bool = False,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """GET /artifact/{workspace_id}/deltas?run_id=...&include_ids=..."""
        client = await get_http_client(self.base_url)
        params = {"run_id": run_id, "include_ids": str(include_ids).lower()}
        headers = _merge_headers(correlation_id=correlation_id)
        resp = await client.get(f"/artifact/{workspace_id}/deltas", params=params, headers=headers)
        _raise_for_status(self.service_name, resp)
        return resp.json()
