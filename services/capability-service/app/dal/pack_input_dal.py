from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from pymongo import ReturnDocument

from app.db.mongo import get_db
from app.models import PackInput, PackInputCreate, PackInputUpdate


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _strip_none(d: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


class PackInputDAL:
    """
    CRUD for PackInput (registry of pack execution inputs).
    Collection: 'pack_inputs'
    """

    def __init__(self):
        self.col = get_db().pack_inputs

    async def create(self, payload: PackInputCreate) -> PackInput:
        doc = PackInput(
            **payload.model_dump(),
            created_at=_utcnow(),
            updated_at=_utcnow(),
        ).model_dump()
        await self.col.insert_one(doc)
        return PackInput.model_validate(doc)

    async def get(self, pack_input_id: str) -> Optional[PackInput]:
        doc = await self.col.find_one({"id": pack_input_id})
        return PackInput.model_validate(doc) if doc else None

    async def delete(self, pack_input_id: str) -> bool:
        res = await self.col.delete_one({"id": pack_input_id})
        return res.deleted_count == 1

    async def update(self, pack_input_id: str, patch: PackInputUpdate) -> Optional[PackInput]:
        update_dict = _strip_none(patch.model_dump())
        update_doc = {"$set": {**update_dict, "updated_at": _utcnow()}}
        doc = await self.col.find_one_and_update(
            {"id": pack_input_id},
            update_doc,
            return_document=ReturnDocument.AFTER,
        )
        return PackInput.model_validate(doc) if doc else None

    async def search(
        self,
        *,
        q: Optional[str] = None,
        tag: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[PackInput], int]:
        filt: Dict[str, Any] = {}
        if tag:
            filt["tags"] = tag
        if q:
            filt["$or"] = [
                {"id": {"$regex": q, "$options": "i"}},
                {"name": {"$regex": q, "$options": "i"}},
                {"description": {"$regex": q, "$options": "i"}},
            ]

        total = await self.col.count_documents(filt)
        cursor = (
            self.col.find(filt)
            .sort("id", 1)
            .skip(max(offset, 0))
            .limit(max(min(limit, 200), 1))
        )
        items = [PackInput.model_validate(d) async for d in cursor]
        return items, total

    async def list_all_ids(self) -> List[str]:
        cursor = self.col.find({}, {"id": 1, "_id": 0}).sort("id", 1)
        return [d["id"] async for d in cursor]