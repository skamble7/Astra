from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────
# Playbooks
# ─────────────────────────────────────────────────────────────

class PlaybookStep(BaseModel):
    id: str
    name: str
    capability_id: str
    description: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)


class Playbook(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    steps: List[PlaybookStep] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────
# Pack
# ─────────────────────────────────────────────────────────────

class PackStatus(str, Enum):
    draft = "draft"
    published = "published"
    archived = "archived"


class CapabilityPack(BaseModel):
    id: str = Field(..., alias="_id")  # key@version
    key: str
    version: str
    title: str
    description: str

    # NEW: reference to a registered pack input contract (optional)
    pack_input_id: Optional[str] = Field(
        default=None,
        description="Id of a PackInput in the registry. Declares the input contract needed to run this pack."
    )

    capability_ids: List[str] = Field(default_factory=list)
    playbooks: List[Playbook] = Field(default_factory=list)

    status: PackStatus = PackStatus.draft

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    published_at: Optional[datetime] = None

    created_by: Optional[str] = None
    updated_by: Optional[str] = None

    model_config = dict(populate_by_name=True)


class CapabilityPackCreate(BaseModel):
    key: str
    version: str
    title: str
    description: str
    pack_input_id: Optional[str] = Field(
        default=None,
        description="Id of a PackInput in the registry."
    )
    capability_ids: List[str] = Field(default_factory=list)
    playbooks: List[Playbook] = Field(default_factory=list)


class CapabilityPackUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    pack_input_id: Optional[str] = None
    capability_ids: Optional[List[str]] = None
    playbooks: Optional[List[Playbook]] = None
    status: Optional[PackStatus] = None