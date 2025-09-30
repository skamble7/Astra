# services/conductor-service/app/clients/artifact_service.py
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.config import settings
from app.clients.http_utils import get_http_client, _raise_for_status, retryable_get

logger = logging.getLogger("app.clients.capability")


class CapabilityServiceClient:
    """
    Thin async client for capability-service.
    Returns plain dicts/lists; we'll add pydantic mirrors later when needed.
    """

    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url = base_url or settings.capability_svc_base_url
        self.service_name = "capability-service"

    # --------- Packs --------- #

    @retryable_get
    async def get_pack_resolved(self, pack_id: str) -> Dict[str, Any]:
        """
        GET /capability/packs/{pack_id}/resolved
        """
        client = await get_http_client(self.base_url)
        url = f"/capability/packs/{pack_id}/resolved"
        resp = await client.get(url)
        _raise_for_status(self.service_name, resp)
        return resp.json()

    @retryable_get
    async def get_pack(self, pack_id: str) -> Dict[str, Any]:
        """
        GET /capability/packs/{pack_id}
        """
        client = await get_http_client(self.base_url)
        url = f"/capability/packs/{pack_id}"
        resp = await client.get(url)
        _raise_for_status(self.service_name, resp)
        return resp.json()

    # --------- Pack Inputs --------- #

    @retryable_get
    async def get_pack_input(self, pack_input_id: str) -> Dict[str, Any]:
        """
        GET /capability/pack-inputs/{pack_input_id}
        """
        client = await get_http_client(self.base_url)
        url = f"/capability/pack-inputs/{pack_input_id}"
        resp = await client.get(url)
        _raise_for_status(self.service_name, resp)
        return resp.json()

    # --------- Capabilities --------- #

    async def get_capability(self, capability_id: str) -> Dict[str, Any]:
        """
        GET /capability/{capability_id}
        """
        client = await get_http_client(self.base_url)
        url = f"/capability/{capability_id}"
        resp = await client.get(url)
        _raise_for_status(self.service_name, resp)
        return resp.json()

    async def get_capabilities_by_ids(self, ids: List[str]) -> List[Dict[str, Any]]:
        """
        POST /capability/by-ids
        """
        client = await get_http_client(self.base_url)
        url = "/capability/by-ids"
        resp = await client.post(url, json={"ids": ids})
        _raise_for_status(self.service_name, resp)
        return resp.json()

    async def search_capabilities(
        self,
        *,
        tag: Optional[str] = None,
        produces_kind: Optional[str] = None,
        mode: Optional[str] = None,
        q: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        GET /capability/search
        """
        client = await get_http_client(self.base_url)
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if tag:
            params["tag"] = tag
        if produces_kind:
            params["produces_kind"] = produces_kind
        if mode:
            params["mode"] = mode
        if q:
            params["q"] = q
        resp = await client.get("/capability/search", params=params)
        _raise_for_status(self.service_name, resp)
        return resp.json()