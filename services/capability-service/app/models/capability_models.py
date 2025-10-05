from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Union, Annotated

from pydantic import BaseModel, Field, AnyUrl, model_validator


# ─────────────────────────────────────────────────────────────
# Common supporting specs
# ─────────────────────────────────────────────────────────────

class RetryPolicy(BaseModel):
    max_attempts: int = Field(default=2, ge=0)
    backoff_ms: int = Field(default=250, ge=0)
    jitter_ms: int = Field(default=50, ge=0)


class DiscoveryPolicy(BaseModel):
    validate_tools: bool = True
    validate_resources: bool = False
    validate_prompts: bool = False
    fail_fast: bool = True


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
    headers: Dict[str, str] = Field(default_factory=dict)  # non-secret only
    auth: Optional[AuthAlias] = None
    timeout_sec: int = Field(default=60, ge=1)
    verify_tls: bool = True
    retry: Optional[RetryPolicy] = None
    health_path: str = "/health"
    protocol_path: str = "/sse"  # protocol endpoint path (e.g., SSE stream or /mcp)


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
# Execution-level I/O contracts
# ─────────────────────────────────────────────────────────────

class ExecutionOutputContract(BaseModel):
    """
    Declares how an execution returns results.

    Discriminator:
      - artifact_type: "cam" | "freeform"

    When artifact_type = "cam":
      - kinds: REQUIRED non-empty list of registered CAM kinds.
      - result_schema: MUST be omitted (None).
      - schema_guide: MAY be provided but is usually unnecessary.
    
    When artifact_type = "freeform":
      - result_schema: REQUIRED JSON Schema describing the result shape.
      - kinds: MUST be omitted or empty.
      - schema_guide: Optional natural-language guidance to help LLMs produce the shape.

    Common optional toggles (apply to both):
      - stream: whether output is streamed.
      - many: whether multiple items are produced (array semantics / item stream).
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
            # kinds required, non-empty; result_schema should be None
            if not self.kinds:
                raise ValueError("ExecutionOutputContract: 'kinds' must be a non-empty list when artifact_type='cam'.")
            if self.result_schema is not None:
                raise ValueError("ExecutionOutputContract: 'result_schema' must be omitted/None when artifact_type='cam'.")
        elif self.artifact_type == "freeform":
            # result_schema required; kinds must be empty
            if self.result_schema is None:
                raise ValueError("ExecutionOutputContract: 'result_schema' is required when artifact_type='freeform'.")
            if self.kinds:
                raise ValueError("ExecutionOutputContract: 'kinds' must be empty/omitted when artifact_type='freeform'.")
        return self


class ExecutionInput(BaseModel):
    """
    Envelope for execution input specification.

    - json_schema: JSON Schema describing the expected input object.
    - schema_guide: Natural-language, field-by-field guidance that helps LLMs/UIs
      construct a valid object (required/optional, allowed values, examples, rules).
      Markdown is allowed.
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
    Execution-level I/O declaration:
    - input_contract: Envelope containing input schema and human-readable guide
    - output_contract: Declares how outputs are shaped (CAM vs freeform), with optional guide
    """
    input_contract: Optional[ExecutionInput] = None
    output_contract: Optional[ExecutionOutputContract] = None


# ─────────────────────────────────────────────────────────────
# MCP ToolCall spec
# ─────────────────────────────────────────────────────────────

class ToolCallSpec(BaseModel):
    tool: str
    args_schema: Optional[Dict[str, Any]] = None
    output_kinds: List[str] = Field(default_factory=list)
    # Optional per-tool non-artifact result envelope (e.g., {job_id, status})
    result_schema: Optional[Dict[str, Any]] = None
    timeout_sec: int = Field(default=60, ge=1)
    retries: int = Field(default=1, ge=0)
    expects_stream: bool = False
    cancellable: bool = True


# ─────────────────────────────────────────────────────────────
# Execution unions
# ─────────────────────────────────────────────────────────────

class McpExecution(BaseModel):
    mode: Literal["mcp"]
    transport: Transport
    tool_calls: List[ToolCallSpec] = Field(default_factory=list)
    discovery: Optional[DiscoveryPolicy] = None
    connection: Optional[Dict[str, bool]] = Field(
        default_factory=lambda: {"singleton": True, "share_across_steps": True}
    )
    # Execution-level input/output contract (envelope with schema + guide)
    io: Optional[ExecutionIO] = None


class LlmParameters(BaseModel):
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)


class LlmExecution(BaseModel):
    mode: Literal["llm"]
    llm_config: Dict[str, Any]  # { provider, model, parameters?: LlmParameters, output_contracts?: [cam.*] }
    # Allow LLM executions to also declare structured I/O if desired
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