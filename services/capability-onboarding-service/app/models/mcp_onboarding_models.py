from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class AuthSpec(BaseModel):
    """
    Auth configuration for an MCP server connection.
    Values here are env-var alias names, NOT raw secrets.
    The service resolves these via os.getenv at connection time.
    """
    method: Literal["none", "bearer", "basic", "api_key"] = "none"
    alias_token: Optional[str] = None       # env var name holding the bearer token
    alias_user: Optional[str] = None        # env var name holding the username
    alias_password: Optional[str] = None    # env var name holding the password
    alias_key: Optional[str] = None         # env var name holding the API key


class ServerConnectionConfig(BaseModel):
    """Connection parameters collected from the UI's 'Connect server' step."""
    base_url: str
    protocol_path: str = "/mcp"
    health_check_path: str = "/health"
    auth: Optional[AuthSpec] = None
    timeout_seconds: int = 180
    verify_tls: bool = False
    headers: Dict[str, str] = Field(default_factory=dict)


class DiscoveredTool(BaseModel):
    """A single tool discovered from the MCP server."""
    name: str
    description: Optional[str] = None
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    output_schema: Optional[Dict[str, Any]] = None


class InferredArtifactKind(BaseModel):
    """An artifact kind inferred by the LLM from the MCP tool schema."""
    kind_id: str            # e.g. "cam.diagram.context"
    kind_name: str          # e.g. "Context Map Diagram"
    category: str           # e.g. "diagram"
    description: Optional[str] = None
    is_new: bool = True     # Set to False at register time if kind already exists
    json_schema: Optional[Dict[str, Any]] = None  # LLM-inferred schema used for kind registration


class InferredCapabilityMeta(BaseModel):
    """LLM-inferred capability metadata for the selected MCP tool.
    Field names match GlobalCapabilityCreate for consistency with the stored model.
    """
    id: str                             # e.g. "cap.domain.discover_context_map"
    name: str
    description: str
    tags: List[str] = Field(default_factory=list)
    produces_kinds: List[InferredArtifactKind] = Field(default_factory=list)


class CapabilityOnboardingDoc(BaseModel):
    """
    Progressive document that travels through the 4-step onboarding wizard.
    Starts sparse (only server config) and gets populated as the user advances.
    """
    # Step 1 — always present
    server: ServerConnectionConfig

    # Step 2 — populated after resolve
    selected_tool: Optional[DiscoveredTool] = None
    available_tools: List[DiscoveredTool] = Field(default_factory=list)

    # Step 3 — populated after LLM inference; editable by user
    inferred: Optional[InferredCapabilityMeta] = None

    # Lifecycle status
    status: Literal["discovered", "inferred", "registered"] = "discovered"

    # Step 4 — populated after successful registration
    registered_capability_id: Optional[str] = None
    registered_kind_ids: List[str] = Field(default_factory=list)


# ── Request / Response models ──────────────────────────────────────────────────

class ResolveRequest(BaseModel):
    """
    Request body for POST /onboarding/resolve.
    If tool_name is None and the server has multiple tools, the response will
    have status='discovered' and available_tools populated for the UI to present
    a picker. Re-POST with tool_name set to proceed to inference.
    """
    server: ServerConnectionConfig
    tool_name: Optional[str] = None


class RegisterRequest(BaseModel):
    """Request body for POST /onboarding/register."""
    doc: CapabilityOnboardingDoc
    dry_run: bool = False  # When True, build payloads and return without persisting


class RegisterResponse(BaseModel):
    """Response from POST /onboarding/register."""
    capability_id: str
    kind_ids_registered: List[str]   # new kinds created in artifact-service
    kind_ids_existing: List[str]     # kinds that already existed
    doc: CapabilityOnboardingDoc     # updated with status="registered"
    # Populated on dry_run=True — exact payloads that would be sent to the services
    capability_payload: Optional[Dict[str, Any]] = None
    kind_payloads: Optional[List[Dict[str, Any]]] = None
