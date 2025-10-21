#services/astraui-resolver-service/app/api/routes.py
from __future__ import annotations

from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..db.mongodb import get_db
from ..models.component import (
    ComponentCreate,
    ComponentUpdate,
    ComponentRead,
    ResolveResponse,
    ComponentListResponse,
)
from ..services.component_service import ComponentService

router = APIRouter()

# ─────────────────────────────────────────────────────────────
# CRUD: register / read / update / delete
# ─────────────────────────────────────────────────────────────
@router.post("/components", response_model=ComponentRead, status_code=status.HTTP_201_CREATED)
async def register_component(
    body: ComponentCreate,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> ComponentRead:
    svc = ComponentService(db)
    item = await svc.upsert(body)
    return item

@router.get("/components/{pack_id}/{region_key}", response_model=ComponentRead)
async def get_component(
    pack_id: str,
    region_key: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> ComponentRead:
    svc = ComponentService(db)
    item = await svc.get(pack_id, region_key)
    if not item:
        raise HTTPException(status_code=404, detail="component mapping not found")
    return item

@router.put("/components/{pack_id}/{region_key}", response_model=ComponentRead)
async def update_component(
    pack_id: str,
    region_key: str,
    body: ComponentUpdate,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> ComponentRead:
    svc = ComponentService(db)
    item = await svc.update(pack_id, region_key, body)
    if not item:
        raise HTTPException(status_code=404, detail="component mapping not found")
    return item

@router.delete("/components/{pack_id}/{region_key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_component(
    pack_id: str,
    region_key: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> None:
    svc = ComponentService(db)
    ok = await svc.delete(pack_id, region_key)
    if not ok:
        raise HTTPException(status_code=404, detail="component mapping not found")

@router.get("/components", response_model=ComponentListResponse)
async def list_components(
    pack_id: Optional[str] = Query(None),
    region_key: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> ComponentListResponse:
    svc = ComponentService(db)
    rows, total = await svc.list(pack_id=pack_id, region_key=region_key, limit=limit, offset=offset)
    return ComponentListResponse(total=total, items=rows)

# ─────────────────────────────────────────────────────────────
# Resolve endpoint
# ─────────────────────────────────────────────────────────────
@router.get("/resolve/{pack_id}/{region_key}", response_model=ResolveResponse)
async def resolve_component(
    pack_id: str,
    region_key: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> ResolveResponse:
    svc = ComponentService(db)
    item = await svc.get(pack_id, region_key)
    if not item:
        raise HTTPException(status_code=404, detail="component not registered for composite key")
    return ResolveResponse(component=item.component_name)