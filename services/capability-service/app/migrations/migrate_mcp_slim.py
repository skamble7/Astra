"""
Migration: Slim MCP capability documents.

Rewrites all MCP capability documents from the verbose format
(tool_calls, io, discovery, connection) to the slim format
(tool_name only).

Run once after deploying the updated capability-service:
    python -m app.migrations.migrate_mcp_slim

Idempotent: documents already in slim format are skipped.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any, Dict, List

from motor.motor_asyncio import AsyncIOMotorClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "astra")


def _extract_tool_name(doc: Dict[str, Any]) -> str | None:
    """Extract tool_name from old or new MCP execution format."""
    execution = doc.get("execution") or {}
    # New format already has tool_name
    if "tool_name" in execution:
        return execution["tool_name"]
    # Old format: tool_calls[0].tool
    tool_calls = execution.get("tool_calls") or []
    if tool_calls:
        first = tool_calls[0]
        return first.get("tool") if isinstance(first, dict) else None
    return None


def _build_slim_execution(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Return a slim execution dict retaining only transport and tool_name."""
    execution = doc.get("execution") or {}
    transport = execution.get("transport") or {}

    # Slim the HTTP transport: drop retry and health_path
    slim_transport: Dict[str, Any] = {k: v for k, v in transport.items()
                                       if k not in ("retry", "health_path")}

    tool_name = _extract_tool_name(doc) or ""

    return {
        "mode": "mcp",
        "transport": slim_transport,
        "tool_name": tool_name,
    }


async def run_migration() -> None:
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[MONGO_DB]
    collection = db["capabilities"]

    cursor = collection.find({"execution.mode": "mcp"})
    docs: List[Dict[str, Any]] = await cursor.to_list(length=None)

    log.info("Found %d MCP capability documents", len(docs))

    migrated = 0
    skipped = 0

    for doc in docs:
        cap_id = doc.get("id", str(doc.get("_id")))
        execution = doc.get("execution") or {}

        # Already slim: has tool_name, no tool_calls/io/discovery/connection
        already_slim = (
            "tool_name" in execution
            and "tool_calls" not in execution
            and "io" not in execution
            and "discovery" not in execution
            and "connection" not in execution
        )
        if already_slim:
            skipped += 1
            log.debug("SKIP %s (already slim)", cap_id)
            continue

        slim_execution = _build_slim_execution(doc)

        result = await collection.update_one(
            {"_id": doc["_id"]},
            {"$set": {"execution": slim_execution}},
        )

        if result.modified_count:
            migrated += 1
            log.info("MIGRATED %s  tool_name=%r", cap_id, slim_execution["tool_name"])
        else:
            log.warning("NO CHANGE for %s", cap_id)

    log.info("Done. migrated=%d skipped=%d total=%d", migrated, skipped, len(docs))
    client.close()


if __name__ == "__main__":
    asyncio.run(run_migration())
