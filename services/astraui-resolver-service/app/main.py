# services/astraui-resolver-service/app/main.py
from __future__ import annotations

import logging
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

from .core.config import settings  # fixed path
from .api.routes import router as api_router
from .db.mongodb import get_db
from .dal.component_dal import ensure_indexes
from .seeds.seed_components import seed_default_components  # NEW

log = logging.getLogger("astraui_resolver.app")

app = FastAPI(
    title="AstraUI Resolver Service",
    version="0.1.0",
    default_response_class=ORJSONResponse,
)

@app.on_event("startup")
async def on_startup() -> None:
    db = await get_db()
    await ensure_indexes(db)
    log.info("AstraUI Resolver Service started. DB indexes ensured.")
    if settings.seed_on_start:
        await seed_default_components(db)
        log.info("Seeds executed (SEED_ON_START=true).")

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": settings.service_name, "port": settings.app_port}

app.include_router(api_router)