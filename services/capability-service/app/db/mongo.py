from __future__ import annotations

from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings

_client: Optional[AsyncIOMotorClient] = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongo_uri)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    return get_client()[settings.mongo_db]


async def init_indexes() -> None:
    db = get_db()

    # capabilities
    await db.capabilities.create_index("id", unique=True)
    await db.capabilities.create_index("tags")
    await db.capabilities.create_index("produces_kinds")
    await db.capabilities.create_index("execution.mode")

    # capability_packs
    await db.capability_packs.create_index([("key", 1), ("version", 1)], unique=True)
    await db.capability_packs.create_index("status")
    await db.capability_packs.create_index("pack_input_id")  # NEW: for quick filtering by input contract
    try:
        await db.capability_packs.create_index([("title", "text"), ("description", "text")])
    except Exception:
        pass

    # pack_inputs
    await db.pack_inputs.create_index("id", unique=True)
    await db.pack_inputs.create_index("name")
    await db.pack_inputs.create_index("tags")