# services/artifact-service/app/seeds/bootstrap.py
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Dict, Any, Set, List, Tuple

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.dal.kind_registry_dal import KINDS, upsert_kind, ensure_registry_indexes
from app.seeds.seed_categories import ensure_categories_seed

# Seed sources (ordered by precedence: earlier wins on _id conflicts)
from app.seeds.seed_registry import KIND_DOCS as ASTRA_KIND_DOCS
# from app.seeds.seed_registry_raina import docs as RAINA_KIND_DOCS
from app.seeds.seed_data_pipeline_registry import KIND_DOCS as DATA_PIPELINE_KIND_DOCS
from app.seeds.seed_kind_registry_cobol_modernization import KIND_DOCS as COBOL_KIND_DOCS

log = logging.getLogger(__name__)

OVERWRITE_ALL = os.getenv("ASTRA_SEED_OVERWRITE", "").strip() in {"1", "true", "True", "yes"}
FORCE_DATA_PIPELINE = os.getenv("ASTRA_SEED_FORCE_DATAPIPELINE", "").strip() in {"1", "true", "True", "yes"}
FORCE_COBOL = os.getenv("ASTRA_SEED_FORCE_COBOL", "").strip() in {"1", "true", "True", "yes"}


def _combine_and_dedupe_kind_docs() -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Merge KIND_DOCS from multiple seed sources in precedence order.
    If duplicate _id values exist, keep the FIRST occurrence.
    Returns (combined_docs, counts_by_name)
    """
    # Name each source explicitly so logging is stable even if some are commented out.
    sources: List[Tuple[str, List[Dict[str, Any]]]] = [
        ("astra", ASTRA_KIND_DOCS),
        # ("raina", RAINA_KIND_DOCS),
        ("data_pipeline", DATA_PIPELINE_KIND_DOCS),
        ("cobol_modernization", COBOL_KIND_DOCS),
    ]

    counts: Dict[str, int] = {}
    combined: List[Dict[str, Any]] = []
    seen: Set[str] = set()

    for name, src in sources:
        counts[name] = len(src)
        for d in src:
            _id = d.get("_id")
            if not _id or _id in seen:
                continue
            combined.append(d)
            seen.add(_id)

    return combined, counts


def _kind_ids(docs: List[Dict[str, Any]]) -> List[str]:
    return [d["_id"] for d in docs if "_id" in d]


async def ensure_registry_seed(db: AsyncIOMotorDatabase) -> Dict[str, Any]:
    """
    Ensures all canonical kind documents exist in the registry.

    Default: insert only missing kinds (no overwrite).
    Env flags:
      - ASTRA_SEED_OVERWRITE=1 → overwrite (upsert) all desired docs.
      - ASTRA_SEED_FORCE_DATAPIPELINE=1 → only seed Data-Pipeline kinds.
      - ASTRA_SEED_FORCE_COBOL=1 → only seed COBOL-modernization kinds.
        (If both FORCE flags are set, COBOL takes precedence.)
    """
    await ensure_registry_indexes(db)
    col = db[KINDS]

    desired_docs, counts = _combine_and_dedupe_kind_docs()

    # Narrow selection if FORCE flags set
    if FORCE_COBOL and FORCE_DATA_PIPELINE:
        log.warning(
            "Both ASTRA_SEED_FORCE_COBOL and ASTRA_SEED_FORCE_DATAPIPELINE are set. "
            "Preferring COBOL kinds only."
        )

    if FORCE_COBOL:
        desired_docs = list(COBOL_KIND_DOCS)  # copy
        log.warning("ASTRA_SEED_FORCE_COBOL=1 → only seeding COBOL-modernization kinds (%d)", len(desired_docs))
    elif FORCE_DATA_PIPELINE:
        desired_docs = list(DATA_PIPELINE_KIND_DOCS)  # copy
        log.warning("ASTRA_SEED_FORCE_DATAPIPELINE=1 → only seeding Data-Pipeline kinds (%d)", len(desired_docs))

    desired_ids = set(_kind_ids(desired_docs))
    existing: Set[str] = {d["_id"] async for d in col.find({}, {"_id": 1})}

    if OVERWRITE_ALL:
        target_ids = sorted(desired_ids)
        mode = "overwrite"
    else:
        missing_ids = sorted(k for k in desired_ids if k not in existing)
        target_ids = missing_ids
        mode = "fresh" if not existing else ("partial" if missing_ids else "skip")

    log.info(
        "Seed sources: astra=%d, data_pipeline=%d, cobol_modernization=%d (combined unique=%d). Existing in DB=%d.",
        counts.get("astra", 0),
        counts.get("data_pipeline", 0),
        counts.get("cobol_modernization", 0),
        len(desired_ids),
        len(existing),
    )
    if not OVERWRITE_ALL and target_ids:
        log.info(
            "Missing (to seed) [%d]: %s",
            len(target_ids),
            ", ".join(target_ids[:50]) + ("..." if len(target_ids) > 50 else "")
        )
    elif not OVERWRITE_ALL and not target_ids:
        log.info("No missing kinds detected; nothing to seed.")

    by_id: Dict[str, Dict[str, Any]] = {d["_id"]: d for d in desired_docs}

    seeded = 0
    now = datetime.utcnow()

    for kind_id in target_ids:
        doc = dict(by_id[kind_id])  # shallow copy
        doc.setdefault("created_at", now)
        doc["updated_at"] = now
        await upsert_kind(db, doc)
        seeded += 1

    log.info(
        "Kind registry seed: mode=%s existing=%d upserts=%d (desired_total=%d)",
        mode, len(existing), seeded, len(desired_ids)
    )
    if seeded and (OVERWRITE_ALL or FORCE_DATA_PIPELINE or FORCE_COBOL):
        log.debug("Upserted kind ids: %s", ", ".join(target_ids))

    return {
        "mode": mode,
        "existing": len(existing),
        "seeded": seeded,
        "desired": len(desired_ids),
        "sources": counts,
        "force_data_pipeline": FORCE_DATA_PIPELINE,
        "force_cobol": FORCE_COBOL,
        "overwrite_all": OVERWRITE_ALL,
    }


async def ensure_all_seeds(db: AsyncIOMotorDatabase) -> Dict[str, Any]:
    kinds_meta = await ensure_registry_seed(db)
    cats_meta = await ensure_categories_seed(db)
    return {"kinds": kinds_meta, "categories": cats_meta}