from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class InferredLLMCapabilityMeta(BaseModel):
    """
    LLM-inferred (and user-editable) metadata for an LLM-mode capability.
    Covers both tabs of the Review & Edit wizard screen:
      - Capability tab: capability_id, name, description, group, tags
      - Artifact kind tab: kind_id, kind_title, kind_category, kind_status,
                           kind_aliases, natural_key, output_schema,
                           system_prompt, strict_json
    """
    # ── Capability tab ────────────────────────────────────────────────────────
    capability_id: str          # cap.<group>.<action>
    name: str
    description: str
    group: str                  # domain | data | diagram | catalog | contract | asset | microservices
    tags: List[str] = Field(default_factory=list)

    # ── Artifact kind tab ─────────────────────────────────────────────────────
    kind_id: str                # cam.<category>.<name>  — also the produces_kind value
    kind_title: str
    kind_category: str          # diagram | data | catalog | contract | asset
    kind_status: Literal["active", "deprecated"] = "active"
    kind_aliases: List[str] = Field(default_factory=list)
    natural_key: Optional[str] = None   # field name in output_schema that acts as stable identity
    output_schema: Dict[str, Any]       # JSON Schema for the artifact kind
    system_prompt: str                  # prompt.system for the kind's schema_version
    strict_json: bool = True
    depends_on: Optional[str] = None    # comma-separated kind IDs → DependsOnSpec.soft[]
    diagram_recipes: List[str] = Field(default_factory=list)  # selected recipe IDs from template list

    # ── Provenance ────────────────────────────────────────────────────────────
    schema_inferred: bool = True  # True when ASTRA generated output_schema (drives AI badge in UI)


class LLMOnboardingDoc(BaseModel):
    """
    Progressive document that travels through the 3-step LLM capability onboarding wizard.
    Populated incrementally: intent inputs (Step 1) → inferred metadata (Step 2) → registered IDs (Step 3).
    """
    # Step 1 — always present
    intent_text: str
    has_schema: bool                            # True → user provided their own schema
    user_schema: Optional[Dict[str, Any]] = None  # Present only when has_schema=True
    llm_config_ref: str                         # ConfigForge ref, e.g. "dev.llm.openai.fast"

    # Step 2 — populated after /llm/infer; editable by user before registering
    inferred: Optional[InferredLLMCapabilityMeta] = None

    # Lifecycle status
    status: Literal["draft", "inferred", "registered"] = "draft"

    # Step 3 — populated after successful registration
    registered_capability_id: Optional[str] = None
    registered_kind_ids: List[str] = Field(default_factory=list)


# ── Request / Response models ──────────────────────────────────────────────────

class LLMInferRequest(BaseModel):
    """Request body for POST /onboarding/llm/infer."""
    intent_text: str
    has_schema: bool = False
    user_schema: Optional[Dict[str, Any]] = None  # Required when has_schema=True
    llm_config_ref: str


class LLMRegisterRequest(BaseModel):
    """Request body for POST /onboarding/llm/register."""
    doc: LLMOnboardingDoc
    dry_run: bool = False  # When True, build payloads and return without persisting


class LLMRegisterResponse(BaseModel):
    """Response from POST /onboarding/llm/register."""
    capability_id: str
    kind_ids_registered: List[str]    # new kinds created in artifact-service
    kind_ids_existing: List[str]      # kinds that already existed (409 absorbed)
    doc: LLMOnboardingDoc             # updated with status="registered"
    # Populated on dry_run=True — exact payloads that would be sent to the services
    capability_payload: Optional[Dict[str, Any]] = None
    kind_payloads: Optional[List[Dict[str, Any]]] = None
