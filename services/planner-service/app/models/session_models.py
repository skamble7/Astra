# services/planner-service/app/models/session_models.py
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class SessionStatus(str, Enum):
    PLANNING = "planning"
    AWAITING_CLARIFICATION = "awaiting_clarification"
    AWAITING_INPUTS = "awaiting_inputs"
    READY_TO_EXECUTE = "ready_to_execute"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatMessage(BaseModel):
    role: MessageRole
    content: str
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PlanStep(BaseModel):
    step_id: str = Field(default_factory=lambda: f"step-{uuid4().hex[:8]}")
    capability_id: str
    title: str
    description: Optional[str] = None
    enabled: bool = True
    inputs: Dict[str, Any] = Field(default_factory=dict)
    run_inputs: Dict[str, Any] = Field(default_factory=dict)  # ADR-009: prefilled MCP form values
    order: int = 0


class PlannerSession(BaseModel):
    session_id: str = Field(default_factory=lambda: uuid4().hex)
    org_id: str
    workspace_id: str
    status: SessionStatus = SessionStatus.PLANNING
    messages: List[ChatMessage] = Field(default_factory=list)
    plan: List[PlanStep] = Field(default_factory=list)
    intent: Optional[Dict[str, Any]] = None
    active_run_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def model_dump_mongo(self) -> Dict[str, Any]:
        d = self.model_dump(mode="json")
        d["_id"] = d["session_id"]
        return d


# ── Request / Response models ───────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    org_id: str
    workspace_id: str
    initial_message: Optional[str] = None


class SendMessageRequest(BaseModel):
    content: str


class UpdatePlanRequest(BaseModel):
    steps: List[PlanStep]


class ApprovePlanRequest(BaseModel):
    workspace_id: Optional[str] = None


class RunRequest(BaseModel):
    strategy: str = "baseline"
    workspace_id: Optional[str] = None
    run_inputs: Dict[str, Any] = Field(default_factory=dict)        # MCP structured form values
    run_text: Optional[str] = None                                   # LLM freetext input
    attachments: List[Dict[str, Any]] = Field(default_factory=list)  # LLM file uploads
