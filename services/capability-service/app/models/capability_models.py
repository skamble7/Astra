from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Union, Annotated

from pydantic import BaseModel, Field, AnyUrl


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
    sse_path: str = "/sse"


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
    Declares how an execution returns artifacts and any extra envelope fields.
    - artifacts_property: name of the property that contains the array of artifacts
    - kinds: list of cam.* kinds the artifacts may contain
    - extra_schema: JSON Schema for non-artifact fields (e.g., job_id, next_cursor)
    - allow_extra_output_fields: if False, response must match artifacts + extra_schema exactly
    """
    artifacts_property: str = Field(default="artifacts", min_length=1)
    kinds: List[str] = Field(default_factory=list)
    extra_schema: Optional[Dict[str, Any]] = None
    allow_extra_output_fields: bool = True


class ExecutionIO(BaseModel):
    """
    Execution-level I/O declaration:
    - input_schema: JSON Schema describing the input parameters for this execution
    - output_contract: how outputs are shaped and validated
    """
    input_schema: Optional[Dict[str, Any]] = None
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
    # NEW: execution-level input/output contract
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