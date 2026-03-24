from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.clients.artifact_client import ArtifactServiceClient
from app.clients.capability_client import CapabilityServiceClient
from app.models.mcp_onboarding_models import (
    CapabilityOnboardingDoc,
    InferredArtifactKind,
    RegisterResponse,
)

logger = logging.getLogger("app.services.registrar")


def _build_kind_payload(kind: InferredArtifactKind) -> Dict[str, Any]:
    """Build a KindRegistryDoc payload for artifact-service POST /registry/kinds.
    Uses the LLM-inferred json_schema when available; falls back to an open schema."""
    if kind.json_schema:
        schema = kind.json_schema
        props_policy = "forbid"
        strict_json = True
    else:
        schema = {
            "type": "object",
            "title": kind.kind_name,
            "description": kind.description or f"Artifact produced by the {kind.kind_name} capability.",
            "additionalProperties": True,
        }
        props_policy = "allow"
        strict_json = False

    return {
        "_id": kind.kind_id,
        "title": kind.kind_name,
        "category": kind.category,
        "status": "active",
        "latest_schema_version": "1.0.0",
        "schema_versions": [
            {
                "version": "1.0.0",
                "json_schema": schema,
                "additional_props_policy": props_policy,
                "prompt": {
                    "system": f"Generate a {kind.kind_name} artifact.",
                    "strict_json": strict_json,
                    "prompt_rev": 1,
                },
            }
        ],
    }


def _build_capability_payload(doc: CapabilityOnboardingDoc) -> Dict[str, Any]:
    """Build the GlobalCapabilityCreate payload for capability-service POST /capability/."""
    meta = doc.inferred
    server = doc.server
    tool = doc.selected_tool

    transport: Dict[str, Any] = {
        "kind": "http",
        "base_url": server.base_url,
        "headers": server.headers,
        "timeout_sec": server.timeout_seconds,
        "verify_tls": server.verify_tls,
        "protocol_path": server.protocol_path,
    }

    # Map AuthSpec → AuthAlias structure expected by capability-service
    if server.auth and server.auth.method != "none":
        transport["auth"] = {
            "method": server.auth.method,
            "alias_token": server.auth.alias_token,
            "alias_user": server.auth.alias_user,
            "alias_password": server.auth.alias_password,
            "alias_key": server.auth.alias_key,
        }
    else:
        transport["auth"] = None

    return {
        "id": meta.id,
        "name": meta.name,
        "description": meta.description,
        "tags": meta.tags,
        "parameters_schema": None,
        "produces_kinds": [k.kind_id for k in meta.produces_kinds],
        "agent": None,
        "execution": {
            "mode": "mcp",
            "transport": transport,
            "tool_name": tool.name,
        },
    }


class Registrar:
    """
    Orchestrates the final registration step:
    1. Conditionally creates new artifact kinds in artifact-service
    2. Creates the capability in capability-service
    """

    def __init__(self) -> None:
        self._cap_client = CapabilityServiceClient()
        self._art_client = ArtifactServiceClient()

    async def register(self, doc: CapabilityOnboardingDoc, dry_run: bool = False) -> RegisterResponse:
        if doc.status != "inferred":
            raise HTTPException(
                status_code=400,
                detail=f"Doc must have status='inferred' before registering. Current status: '{doc.status}'",
            )
        if doc.inferred is None:
            raise HTTPException(status_code=400, detail="Doc is missing inferred metadata.")
        if doc.selected_tool is None:
            raise HTTPException(status_code=400, detail="Doc is missing selected_tool.")

        # Build payloads up front — used for both dry_run preview and actual registration
        capability_payload = _build_capability_payload(doc)
        kind_payloads = [_build_kind_payload(k) for k in doc.inferred.produces_kinds]

        if dry_run:
            return RegisterResponse(
                capability_id=capability_payload["id"],
                kind_ids_registered=[],
                kind_ids_existing=[],
                doc=doc,
                capability_payload=capability_payload,
                kind_payloads=kind_payloads,
            )

        kind_ids_registered: List[str] = []
        kind_ids_existing: List[str] = []

        # Step 1 — Register new artifact kinds (best-effort, non-blocking on error)
        for kind, kpayload in zip(doc.inferred.produces_kinds, kind_payloads):
            try:
                exists = await self._art_client.kind_exists(kind.kind_id)
                if exists:
                    logger.info("[Registrar] Artifact kind already exists: %s", kind.kind_id)
                    kind.is_new = False
                    kind_ids_existing.append(kind.kind_id)
                else:
                    result = await self._art_client.create_kind(kpayload)
                    if result is None:
                        # 409 absorbed — treat as existing
                        kind.is_new = False
                        kind_ids_existing.append(kind.kind_id)
                    else:
                        logger.info("[Registrar] Created artifact kind: %s", kind.kind_id)
                        kind_ids_registered.append(kind.kind_id)
            except Exception as e:
                logger.warning(
                    "[Registrar] Failed to register artifact kind '%s' (non-fatal): %s",
                    kind.kind_id,
                    e,
                )

        # Step 2 — Create capability
        logger.info("[Registrar] Creating capability: %s", capability_payload["id"])

        try:
            created = await self._cap_client.create_capability(capability_payload)
        except Exception as e:
            # Surface 409 (already registered) specifically
            if hasattr(e, "response") and getattr(e.response, "status_code", None) == 409:
                raise HTTPException(
                    status_code=409,
                    detail=f"Capability '{capability_payload['id']}' is already registered.",
                )
            logger.exception("[Registrar] Failed to create capability: %s", e)
            raise HTTPException(
                status_code=502,
                detail=f"Failed to register capability with capability-service: {e}",
            )

        capability_id = created.get("id", capability_payload["id"])
        logger.info("[Registrar] Capability registered successfully: %s", capability_id)

        # Step 3 — Update doc and return
        doc.status = "registered"
        doc.registered_capability_id = capability_id
        doc.registered_kind_ids = kind_ids_registered

        return RegisterResponse(
            capability_id=capability_id,
            kind_ids_registered=kind_ids_registered,
            kind_ids_existing=kind_ids_existing,
            doc=doc,
        )
