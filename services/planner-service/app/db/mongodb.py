# services/planner-service/app/db/mongodb.py
from __future__ import annotations

from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

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

    sessions = db.planner_sessions
    await sessions.create_index([("session_id", ASCENDING)], name="uk_session_id", unique=True)
    await sessions.create_index([("org_id", ASCENDING), ("created_at", DESCENDING)], name="ix_org_created")
    await sessions.create_index([("status", ASCENDING), ("created_at", DESCENDING)], name="ix_status_created")

    runs = db.planner_runs
    await runs.create_index([("run_id", ASCENDING)], name="uk_run_id", unique=True)
    await runs.create_index([("session_id", ASCENDING)], name="ix_session_id")
    await runs.create_index([("workspace_id", ASCENDING), ("created_at", DESCENDING)], name="ix_ws_created")


async def close_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
