# services/capability-service/app/routers/pack_router.py
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.models import CapabilityPack, CapabilityPackCreate, CapabilityPackUpdate, PackStatus
from app.services import PackService, CapabilityService
from app.mcp_schema import resolve_mcp_input_schema

logger = logging.getLogger("app.routers.packs")

router = APIRouter(prefix="/capability/packs", tags=["packs"])
svc = PackService()
cap_svc = CapabilityService()


@router.post("", response_model=CapabilityPack)
async def create_pack(payload: CapabilityPackCreate, actor: Optional[str] = None):
    return await svc.create(payload, actor=actor)


@router.get("", response_model=List[CapabilityPack])
async def list_packs(
    key: Optional[str] = Query(default=None),
    version: Optional[str] = Query(default=None),
    status: Optional[PackStatus] = Query(default=None),
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    items, _ = await svc.search(key=key, version=version, status=status, q=q, limit=limit, offset=offset)
    return items


@router.get("/{pack_id}/playbooks/{playbook_id}/input-schema")
async def get_playbook_input_schema(pack_id: str, playbook_id: str) -> Dict[str, Any]:
    """
    Resolve the input schema for the first MCP capability in a playbook.
    Connects live to the MCP server and returns the tool's JSON Schema.
    """
    pack = await svc.get(pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="Pack not found")

    pb = next((p for p in pack.playbooks if p.id == playbook_id), None)
    if not pb:
        raise HTTPException(status_code=404, detail=f"Playbook '{playbook_id}' not found in pack")

    if not pb.steps:
        raise HTTPException(status_code=422, detail="Playbook has no steps")

    first_cap_id = pb.steps[0].capability_id
    cap = await cap_svc.get(first_cap_id)
    if not cap:
        raise HTTPException(status_code=404, detail=f"Capability '{first_cap_id}' not found")

    exec_cfg = cap.execution
    if getattr(exec_cfg, "mode", None) != "mcp":
        raise HTTPException(
            status_code=422,
            detail=f"First capability '{first_cap_id}' is not mode=mcp (mode={getattr(exec_cfg, 'mode', '?')})"
        )

    transport = exec_cfg.transport.model_dump() if hasattr(exec_cfg.transport, "model_dump") else dict(exec_cfg.transport)
    tool_name: str = getattr(exec_cfg, "tool_name", "") or ""

    result = await resolve_mcp_input_schema(transport=transport, tool_name=tool_name)
    if not result:
        raise HTTPException(
            status_code=503,
            detail=f"Could not resolve input schema from MCP server for capability '{first_cap_id}'"
        )

    logger.info("[input-schema] resolved cap=%s tool=%s props=%s",
                first_cap_id, result.get("tool_name"),
                list((result.get("json_schema") or {}).get("properties", {}).keys()))
    return result


@router.get("/{pack_id}", response_model=CapabilityPack)
async def get_pack(pack_id: str):
    pack = await svc.get(pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="Pack not found")
    return pack


@router.put("/{pack_id}", response_model=CapabilityPack)
async def update_pack(pack_id: str, patch: CapabilityPackUpdate, actor: Optional[str] = None):
    pack = await svc.update(pack_id, patch, actor=actor)
    if not pack:
        raise HTTPException(status_code=404, detail="Pack not found")
    return pack


@router.delete("/{pack_id}")
async def delete_pack(pack_id: str, actor: Optional[str] = None):
    ok = await svc.delete(pack_id, actor=actor)
    if not ok:
        raise HTTPException(status_code=404, detail="Pack not found")
    return {"deleted": True}


@router.post("/{pack_id}/publish", response_model=CapabilityPack)
async def publish_pack(pack_id: str, actor: Optional[str] = None):
    pack = await svc.publish(pack_id, actor=actor)
    if not pack:
        raise HTTPException(status_code=404, detail="Pack not found or not publishable")
    return pack
