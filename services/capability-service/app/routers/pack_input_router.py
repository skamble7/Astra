# services/capability-service/app/routers/pack_input_router.py
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.models import PackInput, PackInputCreate, PackInputUpdate
from app.services.pack_input_service import PackInputService

router = APIRouter(prefix="/capability/pack-inputs", tags=["pack-inputs"])
svc = PackInputService()


@router.post("", response_model=PackInput)
async def create_pack_input(payload: PackInputCreate, actor: Optional[str] = None):
    return await svc.create(payload, actor=actor)


@router.get("", response_model=List[PackInput])
async def list_pack_inputs(
    q: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    items, _ = await svc.search(q=q, tag=tag, limit=limit, offset=offset)
    return items


@router.get("/{pack_input_id}", response_model=PackInput)
async def get_pack_input(pack_input_id: str):
    pi = await svc.get(pack_input_id)
    if not pi:
        raise HTTPException(status_code=404, detail="Pack input not found")
    return pi


@router.put("/{pack_input_id}", response_model=PackInput)
async def update_pack_input(pack_input_id: str, patch: PackInputUpdate, actor: Optional[str] = None):
    pi = await svc.update(pack_input_id, patch, actor=actor)
    if not pi:
        raise HTTPException(status_code=404, detail="Pack input not found")
    return pi


@router.delete("/{pack_input_id}")
async def delete_pack_input(pack_input_id: str, actor: Optional[str] = None):
    ok = await svc.delete(pack_input_id, actor=actor)
    if not ok:
        raise HTTPException(status_code=404, detail="Pack input not found")
    return {"deleted": True}