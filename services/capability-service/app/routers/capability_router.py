# services/capability-service/app/routers/capability_router.py
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.models import GlobalCapability, GlobalCapabilityCreate, GlobalCapabilityUpdate
from app.services import CapabilityService

router = APIRouter(prefix="/capability", tags=["capabilities"])
svc = CapabilityService()


class IdsRequest(BaseModel):
    ids: List[str] = Field(default_factory=list, min_items=1)


@router.post("/", response_model=GlobalCapability)
async def create_capability(payload: GlobalCapabilityCreate, actor: Optional[str] = None):
    return await svc.create(payload, actor=actor)


@router.get("/{capability_id}", response_model=GlobalCapability)
async def get_capability(capability_id: str):
    cap = await svc.get(capability_id)
    if not cap:
        raise HTTPException(status_code=404, detail="Capability not found")
    return cap


@router.post("/by-ids", response_model=List[GlobalCapability])
async def get_capabilities_by_ids(body: IdsRequest):
    """
    Batch fetch capabilities by id. Returns the capabilities in the SAME ORDER
    as provided in `body.ids`. Missing ids are skipped.
    """
    return await svc.get_many(body.ids)


@router.put("/{capability_id}", response_model=GlobalCapability)
async def update_capability(capability_id: str, patch: GlobalCapabilityUpdate, actor: Optional[str] = None):
    cap = await svc.update(capability_id, patch, actor=actor)
    if not cap:
        raise HTTPException(status_code=404, detail="Capability not found")
    return cap


@router.delete("/{capability_id}")
async def delete_capability(capability_id: str, actor: Optional[str] = None):
    ok = await svc.delete(capability_id, actor=actor)
    if not ok:
        raise HTTPException(status_code=404, detail="Capability not found")
    return {"deleted": True}


@router.get("/search", response_model=List[GlobalCapability])
async def search_capabilities(
    tag: Optional[str] = Query(default=None),
    produces_kind: Optional[str] = Query(default=None),
    mode: Optional[str] = Query(default=None, pattern="^(mcp|llm)$"),
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    items, _ = await svc.search(tag=tag, produces_kind=produces_kind, mode=mode, q=q, limit=limit, offset=offset)
    return items