from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

class EventEnvelope(BaseModel):
    """
    Minimal envelope for cross-service parity.
    """
    event: str = Field(..., description="created|updated|started|completed|failed|step.* etc.")
    service: str = Field(..., description="conductor")
    org: str = Field(..., description="Tenant/org segment used in routing key.")
    version: str = Field(default="v1")
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    by: Optional[str] = Field(default=None)
    payload: Dict[str, Any] = Field(default_factory=dict)

class RunEvent(BaseModel):
    run_id: str
    workspace_id: str
    pack_id: str
    playbook_id: Optional[str] = None
    status: Optional[str] = None  # started|running|completed|failed|cancelled
    error: Optional[str] = None

class StepEvent(BaseModel):
    run_id: str
    workspace_id: str
    pack_id: str
    playbook_id: Optional[str] = None
    step_id: str
    status: Optional[str] = None  # started|completed|failed
    metrics: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None