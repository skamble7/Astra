from __future__ import annotations

import logging

from fastapi import APIRouter

from app.models.llm_onboarding_models import (
    LLMInferRequest,
    LLMOnboardingDoc,
    LLMRegisterRequest,
    LLMRegisterResponse,
)
from app.services.diagram_templates import DIAGRAM_RECIPE_TEMPLATES
from app.services.llm_capability_inferencer import LLMCapabilityInferencer
from app.services.llm_registrar import LLMRegistrar

logger = logging.getLogger("app.routers.llm_onboarding")

router = APIRouter(prefix="/onboarding/llm", tags=["llm-onboarding"])


@router.get("/diagram-recipe-templates")
async def get_diagram_recipe_templates():
    """Return the static list of available Mermaid diagram recipe templates."""
    return DIAGRAM_RECIPE_TEMPLATES


@router.post("/infer", response_model=LLMOnboardingDoc)
async def infer(req: LLMInferRequest) -> LLMOnboardingDoc:
    """
    Run ASTRA inference on a free-text capability intent to populate capability
    and artifact kind metadata.

    - When `has_schema=false`: ASTRA infers both the capability metadata AND the
      output JSON Schema from the intent description (`schema_inferred=true`).
    - When `has_schema=true`: provide `user_schema`; ASTRA infers only capability
      metadata and the kind system prompt around the given schema (`schema_inferred=false`).

    Returns an `LLMOnboardingDoc` with `status="inferred"` and `inferred` populated.
    The user may edit the `inferred` block on the Review & Edit screen before registering.
    """
    inferencer = LLMCapabilityInferencer()
    inferred_meta = await inferencer.infer(req)

    return LLMOnboardingDoc(
        intent_text=req.intent_text,
        has_schema=req.has_schema,
        user_schema=req.user_schema,
        llm_config_ref=req.llm_config_ref,
        inferred=inferred_meta,
        status="inferred",
    )


@router.post("/register", response_model=LLMRegisterResponse)
async def register(req: LLMRegisterRequest) -> LLMRegisterResponse:
    """
    Register the LLM capability (and its artifact kind) in ASTRA.

    Expects `doc.status == 'inferred'`. The `doc.inferred` block may have been
    edited by the user on the Review & Edit screen before submitting.

    - The artifact kind is created in artifact-service (best-effort; existing kinds are skipped).
    - The capability is created in capability-service with `execution.mode="llm"`.
    - Returns `doc` updated to `status="registered"` with the registered IDs.
    """
    reg = LLMRegistrar()
    return await reg.register(req.doc, dry_run=req.dry_run)
