# services/workspace-manager-service/app/services/registry_proxy.py
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from ..clients.registry_client import RegistryClient

logger = logging.getLogger("app.services.registry_proxy")


class SchemaValidationError(Exception):
    """Raised when artifact data fails schema validation in artifact-service."""
    pass


class RegistryProxy:
    """
    Drop-in replacement for KindRegistryService.build_envelope() in artifact_routes.py.
    Delegates to artifact-service via HTTP instead of performing registry logic locally.
    """

    def __init__(self, base_url: str) -> None:
        self._client = RegistryClient(base_url)

    async def build_envelope(
        self,
        *,
        kind_or_alias: str,
        name: str,
        data: Dict[str, Any],
        supplied_schema_version: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Calls POST /registry/build-envelope on artifact-service.
        Raises SchemaValidationError on 422, ValueError on 404.
        """
        try:
            return await self._client.build_envelope(
                kind=kind_or_alias,
                name=name,
                data=data,
                schema_version=supplied_schema_version,
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 422:
                detail = _extract_detail(e.response)
                raise SchemaValidationError(detail) from e
            if e.response.status_code == 404:
                raise ValueError(f"Unknown kind '{kind_or_alias}'") from e
            logger.exception("registry build-envelope call failed: %s", e)
            raise


def _extract_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
        return body.get("detail") or str(body)
    except Exception:
        return response.text or "Schema validation failed"
