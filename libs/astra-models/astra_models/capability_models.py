from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Union, Annotated

from pydantic import BaseModel, Field, AnyUrl, model_validator  # AnyUrl used by HTTPTransport


# ─────────────────────────────────────────────────────────────
# Common supporting specs
# ─────────────────────────────────────────────────────────────

class AuthAlias(BaseModel):
    """
    Alias-based auth references (no secrets stored).
    """
    method: Literal["none", "bearer", "basic", "api_key"] = "none"
    alias_token: Optional[str] = None         # bearer
    alias_user: Optional[str] = None          # basic
    alias_password: Optional[str] = None      # basic
    alias_key: Optional[str] = None           # api_key


# ─────────────────────────────────────────────────────────────
# Transports
# ─────────────────────────────────────────────────────────────

class HTTPTransport(BaseModel):
    kind: Literal["http"]
    base_url: Union[AnyUrl, str]
    headers: Dict[str, str] = Field(default_factory=dict)  # non-secret only; used for docker host routing
    auth: Optional[AuthAlias] = None
    timeout_sec: int = Field(default=60, ge=1)
    verify_tls: bool = True
    protocol_path: str = "/mcp"  # determines SSE vs streamable_http transport


class StdioTransport(BaseModel):
    kind: Literal["stdio"]
    command: str
    args: List[str] = Field(default_factory=list)
    cwd: Optional[str] = None
    env: Dict[str, str] = Field(default_factory=dict)          # non-secret only
    env_aliases: Dict[str, str] = Field(default_factory=dict)  # name -> secret alias
    restart_on_exit: bool = True
    readiness_regex: str = "server started"
    kill_timeout_sec: int = Field(default=10, ge=1)


Transport = Annotated[Union[HTTPTransport, StdioTransport], Field(discriminator="kind")]


# ─────────────────────────────────────────────────────────────
# Execution-level I/O contracts (used by LlmExecution)
# ─────────────────────────────────────────────────────────────

class ExecutionOutputContract(BaseModel):
    """
    Declares how an LLM execution returns results.

    Discriminator:
      - artifact_type: "cam" | "freeform"

    When artifact_type = "cam":
      - kinds: REQUIRED non-empty list of registered CAM kinds.
      - result_schema: MUST be omitted (None).
    When artifact_type = "freeform":
      - result_schema: REQUIRED JSON Schema describing the result shape.
      - kinds: MUST be omitted or empty.
    """
    artifact_type: Literal["cam", "freeform"] = Field(default="cam")
    kinds: List[str] = Field(default_factory=list, description="CAM kinds when artifact_type='cam'.")
    result_schema: Optional[Dict[str, Any]] = Field(
        default=None,
        description="JSON Schema for freeform outputs when artifact_type='freeform'."
    )
    schema_guide: Optional[str] = Field(
        default=None,
        description="Text guidance for constructing/validating freeform results; Markdown allowed."
    )
    extra_schema: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def _validate_contract(self) -> "ExecutionOutputContract":
        if self.artifact_type == "cam":
            if not self.kinds:
                raise ValueError("ExecutionOutputContract: 'kinds' must be a non-empty list when artifact_type='cam'.")
            if self.result_schema is not None:
                raise ValueError("ExecutionOutputContract: 'result_schema' must be omitted/None when artifact_type='cam'.")
        elif self.artifact_type == "freeform":
            if self.result_schema is None:
                raise ValueError("ExecutionOutputContract: 'result_schema' is required when artifact_type='freeform'.")
            if self.kinds:
                raise ValueError("ExecutionOutputContract: 'kinds' must be empty/omitted when artifact_type='freeform'.")
        return self


class ExecutionInput(BaseModel):
    """
    Envelope for LLM execution input specification.
    """
    json_schema: Dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema (Draft 2020-12 recommended) for execution input.",
    )
    schema_guide: Optional[str] = Field(
        default=None,
        description="Textual guide for each input field; accepts Markdown.",
    )


class ExecutionIO(BaseModel):
    """
    Execution-level I/O declaration for LLM capabilities.
    """
    input_contract: Optional[ExecutionInput] = None
    output_contract: Optional[ExecutionOutputContract] = None


# ─────────────────────────────────────────────────────────────
# Execution unions
# ─────────────────────────────────────────────────────────────

class McpExecution(BaseModel):
    """
    Slim MCP execution declaration. Schema is discovered live from the MCP server
    via tools/list — only connectivity and identity are stored here.
    """
    mode: Literal["mcp"]
    transport: Transport
    tool_name: str  # the single MCP tool this capability maps to
    io: Optional[ExecutionIO] = None  # optional I/O contract for text-wrapping etc.

    @model_validator(mode="before")
    @classmethod
    def _migrate_verbose_format(cls, data: Any) -> Any:
        """Backward-compat: old docs stored tool_calls list instead of tool_name."""
        if not isinstance(data, dict):
            return data
        if "tool_name" not in data and "tool_calls" in data:
            tool_calls = data.get("tool_calls") or []
            if tool_calls:
                first = tool_calls[0]
                data = dict(data)
                data["tool_name"] = first.get("tool", "") if isinstance(first, dict) else ""
        return data


class LlmExecution(BaseModel):
    mode: Literal["llm"]
    # ConfigForge canonical ref — the conductor fetches the LLM client via RemoteConfigLoader.
    # Example: "dev.llm.openai.fast", "prod.llm.google_genai.astra.primary"
    llm_config_ref: str
    # Allow LLM executions to declare structured I/O if desired
    io: Optional[ExecutionIO] = None


ExecutionUnion = Annotated[Union[McpExecution, LlmExecution], Field(discriminator="mode")]


# ─────────────────────────────────────────────────────────────
# Global Capability
# ─────────────────────────────────────────────────────────────

class GlobalCapability(BaseModel):
    id: str = Field(..., description="Stable capability id, e.g., cap.cobol.copybook.parse")
    name: str
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)

    parameters_schema: Optional[Dict[str, Any]] = None
    produces_kinds: List[str] = Field(default_factory=list)
    agent: Optional[str] = None

    execution: ExecutionUnion

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GlobalCapabilityCreate(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    parameters_schema: Optional[Dict[str, Any]] = None
    produces_kinds: List[str] = Field(default_factory=list)
    agent: Optional[str] = None
    execution: ExecutionUnion


class GlobalCapabilityUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    parameters_schema: Optional[Dict[str, Any]] = None
    produces_kinds: Optional[List[str]] = None
    agent: Optional[str] = None
    execution: Optional[ExecutionUnion] = None
