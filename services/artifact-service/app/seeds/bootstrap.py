# services/artifact-service/app/seeds/bootstrap.py
from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, Any, Set, List

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.dal.kind_registry_dal import KINDS, upsert_kind, ensure_registry_indexes
from app.seeds.seed_categories import ensure_categories_seed

# Import BOTH seed sources:
# - The existing Astra seed (e.g., COBOL/domain seeds)
# - The new Raina→Astra seed (non-diagram kinds you asked to port)
from app.seeds.seed_registry import KIND_DOCS as ASTRA_KIND_DOCS
from app.seeds.seed_registry_raina import docs as RAINA_KIND_DOCS  # list of dicts

log = logging.getLogger(__name__)


def _combine_and_dedupe_kind_docs() -> List[Dict[str, Any]]:
    """
    Merge KIND_DOCS from the existing Astra seed and the new Raina→Astra seed.
    If there are duplicate _id values, keep the FIRST occurrence (Astra seed wins),
    then append the rest from the Raina seed.
    """
    combined: List[Dict[str, Any]] = []
    seen: Set[str] = set()

    # Astra seed first (existing canonical kinds)
    for d in ASTRA_KIND_DOCS:
        _id = d.get("_id")
        if _id and _id not in seen:
            combined.append(d)
            seen.add(_id)

    # Then add Raina→Astra non-diagram kinds
    for d in RAINA_KIND_DOCS:
        _id = d.get("_id")
        if _id and _id not in seen:
            combined.append(d)
            seen.add(_id)

    return combined


def _kind_ids(docs: List[Dict[str, Any]]) -> List[str]:
    return [d["_id"] for d in docs if "_id" in d]


async def ensure_registry_seed(db: AsyncIOMotorDatabase) -> Dict[str, Any]:
    """
    Ensures all canonical kind documents exist in the registry.
    Behavior:
      - Insert only the missing kinds (do NOT mass overwrite existing docs).
      - Adds created_at/updated_at if absent.
      - Merges Astra + Raina (non-diagram) seeds.
    """
    await ensure_registry_indexes(db)
    col = db[KINDS]

    desired_docs = _combine_and_dedupe_kind_docs()
    desired_ids = set(_kind_ids(desired_docs))
    existing: Set[str] = {d["_id"] async for d in col.find({}, {"_id": 1})}
    missing_ids = [k for k in desired_ids if k not in existing]

    # Map for quick access
    by_id: Dict[str, Dict[str, Any]] = {d["_id"]: d for d in desired_docs}

    seeded = 0
    now = datetime.utcnow()

    for kind_id in missing_ids:
        doc = dict(by_id[kind_id])  # shallow copy
        # Ensure common timestamps if not present
        doc.setdefault("created_at", now)
        doc["updated_at"] = now
        await upsert_kind(db, doc)
        seeded += 1

    mode = "fresh" if not existing else ("partial" if missing_ids else "skip")
    log.info(
        "Kind registry seed: mode=%s existing=%d seeded=%d (desired_total=%d)",
        mode, len(existing), seeded, len(desired_ids)
    )
    return {"mode": mode, "existing": len(existing), "seeded": seeded, "desired": len(desired_ids)}


async def ensure_all_seeds(db: AsyncIOMotorDatabase) -> Dict[str, Any]:
    kinds_meta = await ensure_registry_seed(db)
    cats_meta = await ensure_categories_seed(db)
    return {"kinds": kinds_meta, "categories": cats_meta}