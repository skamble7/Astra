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
    # REMOVED: params (step-level params are redundant with capability execution config)


class Playbook(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    # NEW: input_id per playbook (must be in pack_input_ids)
    input_id: Optional[str] = None
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

    # CHANGED: Reference to registered pack input contracts (plural)
    pack_input_ids: List[str] = Field(
        default_factory=list,
        description="Ids of PackInputs in the registry. Declare the input contracts allowed to trigger this pack."
    )

    # Capabilities referenced by playbooks (used within steps)
    capability_ids: List[str] = Field(default_factory=list)

    # Capabilities the agent may use outside explicit playbook steps
    agent_capability_ids: List[str] = Field(
        default_factory=list,
        description="Capability ids required by the agent to execute the pack (not necessarily used as playbook steps)."
    )

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

    # CHANGED: plural inputs at creation time
    pack_input_ids: List[str] = Field(default_factory=list)

    capability_ids: List[str] = Field(default_factory=list)

    # include agent-scoped capability ids at creation time
    agent_capability_ids: List[str] = Field(
        default_factory=list,
        description="Capability ids needed by the agent (outside of playbook steps)."
    )

    playbooks: List[Playbook] = Field(default_factory=list)


class CapabilityPackUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None

    # CHANGED: plural inputs at update time
    pack_input_ids: Optional[List[str]] = None

    capability_ids: Optional[List[str]] = None
    agent_capability_ids: Optional[List[str]] = None

    playbooks: Optional[List[Playbook]] = None
    status: Optional[PackStatus] = None