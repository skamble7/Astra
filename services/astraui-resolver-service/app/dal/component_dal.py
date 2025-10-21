#  services/astraui-resolver-service/app/dal/component_dal.py
from __future__ import annotations

from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, ReturnDocument

COLLECTION = "ui_resolver_components"

def composite_key(pack_id: str, region_key: str) -> str:
    return f"{pack_id.strip()}::{region_key.strip()}".lower()

# ─────────────────────────────────────────────────────────────
# Indexes
# ─────────────────────────────────────────────────────────────
async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    col = db[COLLECTION]
    await col.create_index([("composite_key", ASCENDING)], unique=True)
    await col.create_index([("pack_id", ASCENDING)])
    await col.create_index([("region_key", ASCENDING)])
    await col.create_index([("updated_at", ASCENDING)])

# ─────────────────────────────────────────────────────────────
# CRUD
# ─────────────────────────────────────────────────────────────
async def upsert_component(
    db: AsyncIOMotorDatabase,
    *,
    pack_id: str,
    region_key: str,
    component_name: str,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    now = datetime.utcnow()
    ck = composite_key(pack_id, region_key)
    doc = await db[COLLECTION].find_one_and_update(
        {"composite_key": ck},
        {
            "$set": {
                "pack_id": pack_id,
                "region_key": region_key,
                "composite_key": ck,
                "component_name": component_name,
                "meta": meta or {},
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return doc

async def get_component(
    db: AsyncIOMotorDatabase, *, pack_id: str, region_key: str
) -> Optional[Dict[str, Any]]:
    ck = composite_key(pack_id, region_key)
    return await db[COLLECTION].find_one({"composite_key": ck})

async def update_component(
    db: AsyncIOMotorDatabase,
    *,
    pack_id: str,
    region_key: str,
    component_name: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    ck = composite_key(pack_id, region_key)
    set_fields: Dict[str, Any] = {"updated_at": datetime.utcnow()}
    if component_name is not None:
        set_fields["component_name"] = component_name
    if meta is not None:
        set_fields["meta"] = meta

    doc = await db[COLLECTION].find_one_and_update(
        {"composite_key": ck},
        {"$set": set_fields},
        return_document=ReturnDocument.AFTER,
    )
    return doc

async def delete_component(
    db: AsyncIOMotorDatabase, *, pack_id: str, region_key: str
) -> bool:
    ck = composite_key(pack_id, region_key)
    res = await db[COLLECTION].delete_one({"composite_key": ck})
    return res.deleted_count == 1

async def list_components(
    db: AsyncIOMotorDatabase,
    *,
    pack_id: Optional[str] = None,
    region_key: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    conds: Dict[str, Any] = {}
    if pack_id:
        conds["pack_id"] = pack_id
    if region_key:
        conds["region_key"] = region_key

    cursor = db[COLLECTION].find(conds).sort("updated_at", -1).skip(offset).limit(min(limit, 200))
    items = [d async for d in cursor]
    total = await db[COLLECTION].count_documents(conds)
    return items, total