from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.config import settings
from app.clients.http_utils import get_http_client, _raise_for_status, retryable_get

logger = logging.getLogger("app.clients.artifact")


class ArtifactServiceClient:
    """
    Thin async client for artifact-service.
    Focused on endpoints the conductor needs for runs (baseline fetch, registry kinds, upserts, deltas).
    Returns plain dicts/lists; pydantic mirrors can be added later.
    """

    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url = base_url or settings.artifact_svc_base_url
        self.service_name = "artifact-service"

    # --------- Artifact upserts --------- #

    async def upsert_artifact(
        self,
        workspace_id: str,
        item: Dict[str, Any],
        *,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        POST /artifact/{workspace_id}
        Headers: optional X-Run-Id
        """
        client = await get_http_client(self.base_url)
        url = f"/artifact/{workspace_id}"
        headers = {"X-Run-Id": run_id} if run_id else None
        resp = await client.post(url, json=item, headers=headers)
        _raise_for_status(self.service_name, resp)
        return resp.json()

    async def upsert_batch(
        self,
        workspace_id: str,
        items: List[Dict[str, Any]],
        *,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        POST /artifact/{workspace_id}/upsert-batch
        Headers: optional X-Run-Id
        """
        client = await get_http_client(self.base_url)
        url = f"/artifact/{workspace_id}/upsert-batch"
        headers = {"X-Run-Id": run_id} if run_id else None
        resp = await client.post(url, json={"items": items}, headers=headers)
        _raise_for_status(self.service_name, resp)
        return resp.json()

    # --------- Workspace baseline & artifacts --------- #

    @retryable_get
    async def get_workspace_parent(self, workspace_id: str, *, include_deleted: bool = False) -> Dict[str, Any]:
        """
        GET /artifact/{workspace_id}/parent
        """
        client = await get_http_client(self.base_url)
        resp = await client.get(f"/artifact/{workspace_id}/parent", params={"include_deleted": str(include_deleted).lower()})
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
    ) -> List[Dict[str, Any]]:
        """
        GET /artifact/{workspace_id}
        """
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
        resp = await client.get(f"/artifact/{workspace_id}", params=params)
        _raise_for_status(self.service_name, resp)
        return resp.json()

    @retryable_get
    async def compute_deltas(self, workspace_id: str, *, run_id: str, include_ids: bool = False) -> Dict[str, Any]:
        """
        GET /artifact/{workspace_id}/deltas?run_id=...&include_ids=...
        """
        client = await get_http_client(self.base_url)
        params = {"run_id": run_id, "include_ids": str(include_ids).lower()}
        resp = await client.get(f"/artifact/{workspace_id}/deltas", params=params)
        _raise_for_status(self.service_name, resp)
        return resp.json()

    # --------- Registry (kinds/prompt/validate) --------- #

    @retryable_get
    async def registry_get_kind(self, kind_id: str) -> Dict[str, Any]:
        """
        GET /registry/kinds/{kind_id}
        """
        client = await get_http_client(self.base_url)
        resp = await client.get(f"/registry/kinds/{kind_id}")
        _raise_for_status(self.service_name, resp)
        return resp.json()

    @retryable_get
    async def registry_list_kinds(
        self,
        *,
        status: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """
        GET /registry/kinds
        Returns { "items": [...], "count": N }
        """
        client = await get_http_client(self.base_url)
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        if category:
            params["category"] = category
        resp = await client.get("/registry/kinds", params=params)
        _raise_for_status(self.service_name, resp)
        return resp.json()

    @retryable_get
    async def registry_get_prompt(
        self,
        kind_id: str,
        *,
        version: Optional[str] = None,
        paradigm: Optional[str] = None,
        style: Optional[str] = None,
        format: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        GET /registry/kinds/{kind_id}/prompt
        """
        client = await get_http_client(self.base_url)
        params: Dict[str, Any] = {}
        if version:
            params["version"] = version
        if paradigm:
            params["paradigm"] = paradigm
        if style:
            params["style"] = style
        if format:
            params["format"] = format
        resp = await client.get(f"/registry/kinds/{kind_id}/prompt", params=params)
        _raise_for_status(self.service_name, resp)
        return resp.json()

    async def registry_validate(self, *, kind: str, data: Dict[str, Any], version: Optional[str] = None) -> Dict[str, Any]:
        """
        POST /registry/validate
        """
        client = await get_http_client(self.base_url)
        payload: Dict[str, Any] = {"kind": kind, "data": data}
        if version:
            payload["version"] = version
        resp = await client.post("/registry/validate", json=payload)
        _raise_for_status(self.service_name, resp)
        return resp.json()

    async def registry_adapt(self, kind_id: str, *, data: Dict[str, Any], version: Optional[str] = None) -> Dict[str, Any]:
        """
        POST /registry/kinds/{kind_id}/adapt
        """
        client = await get_http_client(self.base_url)
        params: Dict[str, Any] = {}
        if version:
            params["version"] = version
        resp = await client.post(f"/registry/kinds/{kind_id}/adapt", params=params, json={"data": data})
        _raise_for_status(self.service_name, resp)
        return resp.json()