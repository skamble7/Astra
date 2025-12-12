# services/conductor-service/app/models/run_models.py
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, UUID4, ConfigDict, model_validator


# ─────────────────────────────────────────────────────────────
# Run lifecycle
# ─────────────────────────────────────────────────────────────

class RunStrategy(str, Enum):
    BASELINE = "baseline"
    DELTA = "delta"


class RunStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# ─────────────────────────────────────────────────────────────
# Auditing (MCP + LLM)
# ─────────────────────────────────────────────────────────────

class ToolCallAudit(BaseModel):
    """
    Captures a single MCP tool call or LLM prompt exchange.
    Only one path is expected depending on mode.
    """
    # MCP
    tool_name: Optional[str] = None
    tool_args_preview: Optional[Dict[str, Any]] = None

    # LLM
    system_prompt: Optional[str] = None
    user_prompt: Optional[str] = None
    llm_config: Optional[Dict[str, Any]] = None

    # Shared
    raw_output_sample: Optional[str] = Field(default=None, description="Trimmed sample for troubleshooting")
    validation_errors: List[str] = Field(default_factory=list)
    duration_ms: Optional[int] = None

    # Keep the canonical vocabulary; normalize inputs like "error" → "failed"
    status: Literal["ok", "retried", "failed"] = "ok"

    @model_validator(mode="before")
    @classmethod
    def _normalize_status(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize various incoming status strings to our canonical set.
        Examples: "error" -> "failed", "success" -> "ok", "retry" -> "retried".
        """
        raw = (values or {}).get("status")
        if raw is None:
            return values

        s = str(raw).strip().lower()
        if not s:
            values["status"] = "failed"
            return values

        mapping = {
            "ok": "ok",
            "success": "ok",
            "succeeded": "ok",
            "completed": "ok",

            "retried": "retried",
            "retry": "retried",
            "retriable": "retried",

            "failed": "failed",
            "fail": "failed",
            "failure": "failed",
            "error": "failed",
            "exception": "failed",
        }

        values["status"] = mapping.get(s, "failed")
        return values


class StepAudit(BaseModel):
    step_id: str
    capability_id: str
    mode: Literal["mcp", "llm"]
    inputs_preview: Dict[str, Any] = Field(default_factory=dict)
    calls: List[ToolCallAudit] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────
# Produced artifacts (envelope only; full persistence lives in artifact-service)
# ─────────────────────────────────────────────────────────────

class ArtifactProvenance(BaseModel):
    run_id: UUID4
    step_id: str
    capability_id: str
    mode: Literal["mcp", "llm"]
    inputs_hash: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ArtifactEnvelope(BaseModel):
    """
    The conductor owns DELTA run artifacts (not workspace baseline).
    The artifact-service owns the promoted baseline artifacts.
    """
    kind_id: str
    schema_version: str
    identity: Dict[str, Any]
    data: Dict[str, Any]
    diagrams: List[Dict[str, Any]] = Field(default_factory=list)
    narratives: List[Dict[str, Any]] = Field(default_factory=list)
    provenance: ArtifactProvenance


# ─────────────────────────────────────────────────────────────
# Diffs summary (optionally populated by conductor or fetched from artifact-service)
# ─────────────────────────────────────────────────────────────

class ChangedArtifact(BaseModel):
    kind_id: str
    identity: Dict[str, Any]
    before: Dict[str, Any]
    after: Dict[str, Any]


class ArtifactsDiffBuckets(BaseModel):
    added: List[ArtifactEnvelope] = Field(default_factory=list)
    changed: List[ChangedArtifact] = Field(default_factory=list)
    unchanged: List[ArtifactEnvelope] = Field(default_factory=list)
    removed: List[ArtifactEnvelope] = Field(default_factory=list)


class RunDeltas(BaseModel):
    counts: Dict[str, int] = Field(default_factory=dict)


# ─────────────────────────────────────────────────────────────
# Validation issues captured during the run
# ─────────────────────────────────────────────────────────────

class ValidationIssue(BaseModel):
    artifact_key: Dict[str, Any] = Field(default_factory=dict)  # minimally {kind_id, identity:{...}}
    severity: Literal["low", "medium", "high"] = "medium"
    message: str


# ─────────────────────────────────────────────────────────────
# Step state (lightweight runtime state persisted in run doc)
# ─────────────────────────────────────────────────────────────

class StepState(BaseModel):
    step_id: str
    capability_id: str
    name: Optional[str] = None
    status: StepStatus = StepStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    metrics: Dict[str, Any] = Field(default_factory=dict)


# ─────────────────────────────────────────────────────────────
# Requests & persisted run doc
# ─────────────────────────────────────────────────────────────

class StartRunRequest(BaseModel):
    """
    Conductor API request shape to start a run.
    Inputs are a free-form object validated against the pack's Pack Input (via capability-service).
    """
    playbook_id: str
    pack_id: str
    workspace_id: UUID4

    inputs: Dict[str, Any] = Field(default_factory=dict)  # validated against pack_input.json_schema

    # Friendly metadata for run
    title: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)

    # Strategy (baseline|delta). If omitted, conductor decides based on workspace state.
    strategy: Optional[RunStrategy] = None


class RunSummary(BaseModel):
    validations: List[ValidationIssue] = Field(default_factory=list)
    logs: List[str] = Field(default_factory=list)
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_s: Optional[float] = None


class PlaybookRun(BaseModel):
    """
    Single collection: pack_runs (owned by conductor).
    Baseline artifacts live in artifact-service; we store DELTA artifacts for promotion UX.
    """
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    run_id: UUID4 = Field(default_factory=uuid4)

    # identity & intent
    workspace_id: UUID4
    pack_id: str
    playbook_id: str
    strategy: RunStrategy = RunStrategy.DELTA

    # inputs
    pack_input_id: Optional[str] = None
    inputs: Dict[str, Any] = Field(default_factory=dict)
    input_fingerprint: Optional[str] = None  # sha256 over canonical(inputs)

    # runtime state
    status: RunStatus = RunStatus.CREATED
    steps: List[StepState] = Field(default_factory=list)

    # outputs & diffs
    run_artifacts: List[ArtifactEnvelope] = Field(default_factory=list)           # DELTA artifacts owned by conductor
    diffs_by_kind: Dict[str, ArtifactsDiffBuckets] = Field(default_factory=dict)  # optional, if computed here
    deltas: Optional[RunDeltas] = None

    # audit trail
    notes_md: Optional[str] = None
    audit: List[StepAudit] = Field(default_factory=list)

    # metadata
    title: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # minimal summary (denormalized)
    run_summary: Optional[RunSummary] = None