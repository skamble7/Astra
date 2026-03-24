from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.clients.artifact_client import ArtifactServiceClient
from app.clients.capability_client import CapabilityServiceClient
from app.models.llm_onboarding_models import (
    InferredLLMCapabilityMeta,
    LLMOnboardingDoc,
    LLMRegisterResponse,
)

logger = logging.getLogger("app.services.llm_registrar")


def _build_kind_payload(meta: InferredLLMCapabilityMeta) -> Dict[str, Any]:
    """Build a KindRegistryDoc payload for artifact-service POST /registry/kinds."""
    props_policy = "forbid" if meta.strict_json else "allow"

    kind_payload: Dict[str, Any] = {
        "_id": meta.kind_id,
        "title": meta.kind_title,
        "category": meta.kind_category,
        "status": meta.kind_status,
        "latest_schema_version": "1.0.0",
        "schema_versions": [
            {
                "version": "1.0.0",
                "json_schema": meta.output_schema,
                "additional_props_policy": props_policy,
                "prompt": {
                    "system": meta.system_prompt,
                    "strict_json": meta.strict_json,
                    "prompt_rev": 1,
                },
            }
        ],
    }

    if meta.kind_aliases:
        kind_payload["aliases"] = meta.kind_aliases

    if meta.natural_key:
        kind_payload["schema_versions"][0]["identity"] = {"natural_key": meta.natural_key}

    return kind_payload


def _build_capability_payload(doc: LLMOnboardingDoc) -> Dict[str, Any]:
    """Build the GlobalCapabilityCreate payload for capability-service POST /capability/."""
    meta = doc.inferred

    return {
        "id": meta.capability_id,
        "name": meta.name,
        "description": meta.description,
        "tags": meta.tags,
        "parameters_schema": None,
        "produces_kinds": [meta.kind_id],
        "agent": None,
        "execution": {
            "mode": "llm",
            "llm_config_ref": doc.llm_config_ref,
        },
    }


class LLMRegistrar:
    """
    Orchestrates the final registration step for LLM-mode capabilities:
    1. Conditionally creates the artifact kind in artifact-service
    2. Creates the capability in capability-service with execution.mode="llm"
    """

    def __init__(self) -> None:
        self._cap_client = CapabilityServiceClient()
        self._art_client = ArtifactServiceClient()

    async def register(self, doc: LLMOnboardingDoc, dry_run: bool = False) -> LLMRegisterResponse:
        if doc.status != "inferred":
            raise HTTPException(
                status_code=400,
                detail=f"Doc must have status='inferred' before registering. Current status: '{doc.status}'",
            )
        if doc.inferred is None:
            raise HTTPException(status_code=400, detail="Doc is missing inferred metadata.")

        capability_payload = _build_capability_payload(doc)
        kind_payload = _build_kind_payload(doc.inferred)

        if dry_run:
            return LLMRegisterResponse(
                capability_id=capability_payload["id"],
                kind_ids_registered=[],
                kind_ids_existing=[],
                doc=doc,
                capability_payload=capability_payload,
                kind_payloads=[kind_payload],
            )

        kind_ids_registered: List[str] = []
        kind_ids_existing: List[str] = []
        kind_id = doc.inferred.kind_id

        # Step 1 — Register artifact kind (best-effort, non-blocking on error)
        try:
            exists = await self._art_client.kind_exists(kind_id)
            if exists:
                logger.info("[LLMRegistrar] Artifact kind already exists: %s", kind_id)
                kind_ids_existing.append(kind_id)
            else:
                result = await self._art_client.create_kind(kind_payload)
                if result is None:
                    # 409 absorbed — treat as existing
                    kind_ids_existing.append(kind_id)
                else:
                    logger.info("[LLMRegistrar] Created artifact kind: %s", kind_id)
                    kind_ids_registered.append(kind_id)
        except Exception as e:
            logger.warning(
                "[LLMRegistrar] Failed to register artifact kind '%s' (non-fatal): %s",
                kind_id,
                e,
            )

        # Step 2 — Create capability
        logger.info("[LLMRegistrar] Creating capability: %s", capability_payload["id"])

        try:
            created = await self._cap_client.create_capability(capability_payload)
        except Exception as e:
            if hasattr(e, "response") and getattr(e.response, "status_code", None) == 409:
                raise HTTPException(
                    status_code=409,
                    detail=f"Capability '{capability_payload['id']}' is already registered.",
                )
            logger.exception("[LLMRegistrar] Failed to create capability: %s", e)
            raise HTTPException(
                status_code=502,
                detail=f"Failed to register capability with capability-service: {e}",
            )

        capability_id = created.get("id", capability_payload["id"])
        logger.info("[LLMRegistrar] Capability registered successfully: %s", capability_id)

        # Step 3 — Update doc and return
        doc.status = "registered"
        doc.registered_capability_id = capability_id
        doc.registered_kind_ids = kind_ids_registered

        return LLMRegisterResponse(
            capability_id=capability_id,
            kind_ids_registered=kind_ids_registered,
            kind_ids_existing=kind_ids_existing,
            doc=doc,
        )
