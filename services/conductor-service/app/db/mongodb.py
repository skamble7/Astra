# services/conductor-service/app/db/mongodb.py
from __future__ import annotations

from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

from app.config import settings

_client: Optional[AsyncIOMotorClient] = None


def get_client() -> AsyncIOMotorClient:
    """
    Singleton Motor client for the conductor-service.
    """
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongo_uri)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    """
    Default database selected by settings.mongo_db.
    """
    return get_client()[settings.mongo_db]


async def init_indexes() -> None:
    """
    Create minimal indexes for the conductor-owned collection(s).
    We keep the DAL in app/db/run_repository.py, but mirror index creation here
    to match the pattern used in capability-service.
    """
    db = get_db()
    runs = db.pack_runs  # type: ignore[attr-defined]

    # Uniqueness on run id (UUID4 stored as string)
    await runs.create_index([("run_id", ASCENDING)], name="uk_run_id", unique=True)

    # Common query paths
    await runs.create_index(
        [("workspace_id", ASCENDING), ("created_at", DESCENDING)],
        name="ix_ws_created",
    )
    await runs.create_index(
        [("status", ASCENDING), ("created_at", DESCENDING)],
        name="ix_status_created",
    )
    await runs.create_index([("pack_id", ASCENDING)], name="ix_pack_id")
    await runs.create_index([("playbook_id", ASCENDING)], name="ix_playbook_id")


async def close_client() -> None:
    """
    Optional graceful shutdown hook (call from app lifespan).
    """
    global _client
    if _client is not None:
        _client.close()
        _client = None