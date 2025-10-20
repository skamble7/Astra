# services/capability-service/app/routers/pack_input_router.py
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.models import PackInput, PackInputCreate, PackInputUpdate
from app.services.pack_input_service import PackInputService
from app.services import PackService  # NEW

router = APIRouter(prefix="/capability/pack-inputs", tags=["pack-inputs"])
svc = PackInputService()
pack_svc = PackService()  # NEW


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


# ─────────────────────────────────────────────────────────────
# NEW: Resolve PackInput for a given pack + playbook_id
# ─────────────────────────────────────────────────────────────
@router.get("/by-pack/{pack_id}/playbook/{playbook_id}", response_model=PackInput)
async def get_pack_input_for_playbook(pack_id: str, playbook_id: str):
    """
    Returns the PackInput (input contract) used by the given playbook within the specified pack.

    Resolution rules:
      1) If the playbook has `input_id`, use it.
      2) Else, if the pack declares exactly one `pack_input_id`, use that.
      3) Else, 400 (ambiguous or missing).
    """
    pack = await pack_svc.get(pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="Pack not found")

    # Locate the playbook by id
    playbook = None
    for pb in (pack.playbooks or []):
        if getattr(pb, "id", None) == playbook_id:
            playbook = pb
            break
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook not found in pack")

    # Determine input_id
    input_id = getattr(playbook, "input_id", None)
    declared_inputs = list(getattr(pack, "pack_input_ids", []) or [])

    if input_id:
        # Validate playbook input membership (enforced elsewhere too, but keep router resilient)
        if declared_inputs and input_id not in declared_inputs:
            raise HTTPException(
                status_code=400,
                detail=f"Playbook input_id '{input_id}' is not in pack_input_ids {sorted(declared_inputs)}",
            )
    else:
        # No explicit playbook input: infer if the pack has exactly one allowed input
        if len(declared_inputs) == 1:
            input_id = declared_inputs[0]
        elif len(declared_inputs) == 0:
            raise HTTPException(
                status_code=400,
                detail="No input_id on playbook and pack declares no pack_input_ids.",
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"No input_id on playbook and multiple pack_input_ids exist {sorted(declared_inputs)}; cannot infer uniquely.",
            )

    # Fetch and return the registered PackInput
    pi = await svc.get(input_id)
    if not pi:
        raise HTTPException(
            status_code=404,
            detail=f"Pack input '{input_id}' not found in registry",
        )
    return pi