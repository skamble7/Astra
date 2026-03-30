# services/conductor-service/app/clients/artifact_service.py
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.config import settings
from app.clients.http_utils import get_http_client, _raise_for_status, retryable_get

logger = logging.getLogger("app.clients.artifact")


def _merge_headers(
    *,
    correlation_id: Optional[str] = None,
    extras: Optional[Dict[str, str]] = None,
) -> Optional[Dict[str, str]]:
    """Build per-request headers (X-Correlation-Id + any extras)."""
    headers: Dict[str, str] = {}
    if correlation_id:
        headers["X-Correlation-Id"] = correlation_id
    if extras:
        headers.update({k: v for k, v in extras.items() if v is not None})
    return headers or None


class ArtifactServiceClient:
    """
    Thin async client for artifact-service.

    NOTE: Exposes both the original `registry_*` methods and adapter-friendly
    aliases (`get_kind`, `list_kinds`, `get_prompt`, `validate`, `adapt`) and
    all of them now accept an optional `correlation_id` that is forwarded as
    X-Correlation-Id.
    """

    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url = base_url or settings.artifact_svc_base_url
        self.service_name = "artifact-service"

    # ---------------------------------------------------------------------
    # Registry (original names)
    # ---------------------------------------------------------------------
    @retryable_get
    async def registry_get_kind(self, kind_id: str, *, correlation_id: Optional[str] = None) -> Dict[str, Any]:
        """
        GET /registry/kinds/{kind_id}
        """
        client = await get_http_client(self.base_url)
        headers = _merge_headers(correlation_id=correlation_id)
        resp = await client.get(f"/registry/kinds/{kind_id}", headers=headers)
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
        correlation_id: Optional[str] = None,
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
        headers = _merge_headers(correlation_id=correlation_id)
        resp = await client.get("/registry/kinds", params=params, headers=headers)
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
        correlation_id: Optional[str] = None,
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
        headers = _merge_headers(correlation_id=correlation_id)
        resp = await client.get(f"/registry/kinds/{kind_id}/prompt", params=params, headers=headers)
        _raise_for_status(self.service_name, resp)
        return resp.json()

    async def registry_validate(
        self,
        *,
        kind: str,
        data: Dict[str, Any],
        version: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        POST /registry/validate
        """
        client = await get_http_client(self.base_url)
        payload: Dict[str, Any] = {"kind": kind, "data": data}
        if version:
            payload["version"] = version
        headers = _merge_headers(correlation_id=correlation_id)
        resp = await client.post("/registry/validate", json=payload, headers=headers)
        _raise_for_status(self.service_name, resp)
        return resp.json()

    async def registry_adapt(
        self,
        kind_id: str,
        *,
        data: Dict[str, Any],
        version: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        POST /registry/kinds/{kind_id}/adapt
        """
        client = await get_http_client(self.base_url)
        params: Dict[str, Any] = {}
        if version:
            params["version"] = version
        headers = _merge_headers(correlation_id=correlation_id)
        resp = await client.post(f"/registry/kinds/{kind_id}/adapt", params=params, json={"data": data}, headers=headers)
        _raise_for_status(self.service_name, resp)
        return resp.json()

    @retryable_get
    async def get_kind_schema(
        self,
        kind_id: str,
        version: str,
        *,
        correlation_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        GET /registry/kinds/{kind_id}/schema/{version}
        Returns None on 404.
        """
        client = await get_http_client(self.base_url)
        headers = _merge_headers(correlation_id=correlation_id)
        resp = await client.get(f"/registry/kinds/{kind_id}/schema/{version}", headers=headers)
        if resp.status_code == 404:
            return None
        _raise_for_status(self.service_name, resp)
        return resp.json()

    # ---------------------------------------------------------------------
    # Adapter-friendly aliases (expected by KindSchemaRegistry / ArtifactAdapter)
    # ---------------------------------------------------------------------
    @retryable_get
    async def get_kind(self, kind_id: str, *, correlation_id: Optional[str] = None) -> Dict[str, Any]:
        """Alias for registry_get_kind(kind_id)."""
        return await self.registry_get_kind(kind_id, correlation_id=correlation_id)

    @retryable_get
    async def list_kinds(
        self,
        *,
        status: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Alias for registry_list_kinds(...)."""
        return await self.registry_list_kinds(
            status=status, category=category, limit=limit, offset=offset, correlation_id=correlation_id
        )

    @retryable_get
    async def get_prompt(
        self,
        kind_id: str,
        *,
        version: Optional[str] = None,
        paradigm: Optional[str] = None,
        style: Optional[str] = None,
        format: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Alias for registry_get_prompt(...)."""
        return await self.registry_get_prompt(
            kind_id,
            version=version,
            paradigm=paradigm,
            style=style,
            format=format,
            correlation_id=correlation_id,
        )

    async def validate(
        self,
        *,
        kind: str,
        data: Dict[str, Any],
        version: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Alias for registry_validate(...)."""
        return await self.registry_validate(kind=kind, data=data, version=version, correlation_id=correlation_id)

    async def adapt(
        self,
        kind_id: str,
        *,
        data: Dict[str, Any],
        version: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Alias for registry_adapt(...)."""
        return await self.registry_adapt(kind_id, data=data, version=version, correlation_id=correlation_id)