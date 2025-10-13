# services/capability-service/app/models/pack_input_models.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PackInput(BaseModel):
    """
    Registry model describing an input contract that a Capability Pack
    can depend on. It is intentionally decoupled from packs/playbooks.
    """
    id: str = Field(..., description="Stable input id (e.g., input.renova.repo)")
    name: str
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)

    # NOTE: use `json_schema` to avoid clashes with pydantic internals.
    json_schema: Dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema (Draft 2020-12 recommended) describing input payload shape."
    )

    examples: List[Dict[str, Any]] = Field(default_factory=list, description="Optional example payloads.")

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PackInputCreate(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    json_schema: Dict[str, Any] = Field(default_factory=dict)
    examples: List[Dict[str, Any]] = Field(default_factory=list)


class PackInputUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    json_schema: Optional[Dict[str, Any]] = None
    examples: Optional[List[Dict[str, Any]]] = None