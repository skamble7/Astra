# services/astraui-resolver-service/app/seeds/seed_components.py
from __future__ import annotations

import os
import logging
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..models.component import ComponentCreate
from ..services.component_service import ComponentService

log = logging.getLogger("astraui_resolver.seeds")

# Defaults are overridable via env for flexibility
DEFAULT_PACK_ID = os.getenv("SEED_PACK_ID", "cobol-mainframe@v1.0.1")
DEFAULT_REGION_KEY = os.getenv("SEED_REGION_KEY", "region.overview")
DEFAULT_COMPONENT_NAME = os.getenv("SEED_COMPONENT_NAME", "RainaOverview")


async def seed_default_components(db: AsyncIOMotorDatabase) -> None:
    """
    Idempotently register a default mapping:
      composite key: pack_id + '::' + region_key (lowercased)
      value: component_name (React component to render)
    """
    svc = ComponentService(db)

    payload = ComponentCreate(
        pack_id=DEFAULT_PACK_ID,
        region_key=DEFAULT_REGION_KEY,
        component_name=DEFAULT_COMPONENT_NAME,
        meta={"seeded": True, "note": "initial default mapping for Overview region"},
    )

    item = await svc.upsert(payload)
    log.info(
        "[seed] component mapping ensured: %s -> %s",
        f"{item.pack_id}::{item.region_key}",
        item.component_name,
    )