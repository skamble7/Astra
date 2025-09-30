# services/capability-service/app/services/pack_input_service.py
from __future__ import annotations

from typing import List, Optional, Tuple

from app.dal.pack_input_dal import PackInputDAL
from app.events import get_bus
from app.models import PackInput, PackInputCreate, PackInputUpdate


class PackInputService:
    def __init__(self) -> None:
        self.dal = PackInputDAL()

    # CRUD
    async def create(self, payload: PackInputCreate, *, actor: Optional[str] = None) -> PackInput:
        pi = await self.dal.create(payload)
        try:
            await get_bus().publish(
                service="capability",
                event="pack_input.created",
                payload={"id": pi.id, "name": pi.name, "tags": pi.tags, "by": actor},
            )
        except Exception:
            # Non-fatal if bus not available
            pass
        return pi

    async def get(self, pack_input_id: str) -> Optional[PackInput]:
        return await self.dal.get(pack_input_id)

    async def update(self, pack_input_id: str, patch: PackInputUpdate, *, actor: Optional[str] = None) -> Optional[PackInput]:
        pi = await self.dal.update(pack_input_id, patch)
        if pi:
            try:
                await get_bus().publish(
                    service="capability",
                    event="pack_input.updated",
                    payload={"id": pi.id, "name": pi.name, "tags": pi.tags, "by": actor},
                )
            except Exception:
                pass
        return pi

    async def delete(self, pack_input_id: str, *, actor: Optional[str] = None) -> bool:
        ok = await self.dal.delete(pack_input_id)
        if ok:
            try:
                await get_bus().publish(
                    service="capability",
                    event="pack_input.deleted",
                    payload={"id": pack_input_id, "by": actor},
                )
            except Exception:
                pass
        return ok

    async def search(
        self,
        *,
        q: Optional[str] = None,
        tag: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[PackInput], int]:
        return await self.dal.search(q=q, tag=tag, limit=limit, offset=offset)

    async def list_all_ids(self) -> List[str]:
        return await self.dal.list_all_ids()