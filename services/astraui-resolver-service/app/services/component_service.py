# services/astraui-resolver-service/app/services/component_service.py
from __future__ import annotations

from typing import Optional, Tuple, List, Dict, Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from ..models.component import ComponentCreate, ComponentUpdate, ComponentRead
from ..dal import component_dal

class ComponentService:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.db = db

    async def upsert(self, body: ComponentCreate) -> ComponentRead:
        doc = await component_dal.upsert_component(
            self.db,
            pack_id=body.pack_id,
            region_key=body.region_key,
            component_name=body.component_name,
            meta=body.meta or {},
        )
        return ComponentRead(**doc)

    async def get(self, pack_id: str, region_key: str) -> Optional[ComponentRead]:
        doc = await component_dal.get_component(self.db, pack_id=pack_id, region_key=region_key)
        return ComponentRead(**doc) if doc else None

    async def update(self, pack_id: str, region_key: str, body: ComponentUpdate) -> Optional[ComponentRead]:
        doc = await component_dal.update_component(
            self.db,
            pack_id=pack_id,
            region_key=region_key,
            component_name=body.component_name,
            meta=body.meta,
        )
        return ComponentRead(**doc) if doc else None

    async def delete(self, pack_id: str, region_key: str) -> bool:
        return await component_dal.delete_component(self.db, pack_id=pack_id, region_key=region_key)

    async def list(
        self,
        *,
        pack_id: Optional[str] = None,
        region_key: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[ComponentRead], int]:
        rows, total = await component_dal.list_components(
            self.db, pack_id=pack_id, region_key=region_key, limit=limit, offset=offset
        )
        return [ComponentRead(**r) for r in rows], total