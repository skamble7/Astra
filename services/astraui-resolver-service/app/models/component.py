# services/astraui-resolver-service/app/models/component.py
from __future__ import annotations

from datetime import datetime
from typing import Optional, Dict, Any, List

from pydantic import BaseModel, Field

# Input models
class ComponentCreate(BaseModel):
    pack_id: str = Field(..., min_length=1, description="Capability pack identifier")
    region_key: str = Field(..., min_length=1, description="UI region key, e.g. 'region.overview'")
    component_name: str = Field(..., min_length=1, description="React component name to render")
    meta: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Optional metadata")

class ComponentUpdate(BaseModel):
    component_name: Optional[str] = Field(None, min_length=1)
    meta: Optional[Dict[str, Any]] = None

# Output models
class ComponentRead(BaseModel):
    pack_id: str
    region_key: str
    composite_key: str
    component_name: str
    meta: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

class ResolveResponse(BaseModel):
    component: str

class ComponentListResponse(BaseModel):
    total: int
    items: List[ComponentRead]