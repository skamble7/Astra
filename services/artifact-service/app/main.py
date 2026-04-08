# services/artifact-service/app/main.py
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .logging_conf import configure_logging
from .routers.registry_routes import router as registry_router
from .routers.category_routes import router as category_router
from .db.mongodb import get_db
from .dal.kind_registry_dal import ensure_registry_indexes
from .services.openapi_typing import compile_discriminated_union, patch_routes_with_union
from .seeds.bootstrap import ensure_all_seeds
from .config import settings
from .middleware.correlation import CorrelationIdMiddleware, CorrelationIdFilter

configure_logging()
log = logging.getLogger(__name__)

_corr_filter = CorrelationIdFilter()
for name in ("", "uvicorn.access", "uvicorn.error", __name__.split(".")[0] or "app"):
    logging.getLogger(name).addFilter(_corr_filter)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = await get_db()

    await ensure_registry_indexes(db)
    log.info("Mongo indexes ensured for kind registry")

    # Seed registry + categories (idempotent)
    try:
        seed_meta = await ensure_all_seeds(db)
        log.info("Seeding result: %s", seed_meta)
    except Exception as e:
        log.exception("Seeding failed: %s", e)

    # Build OpenAPI typing dynamically from registry
    try:
        union_type, models, versions = await compile_discriminated_union(db)
        if union_type is not None:
            patch_routes_with_union(app, union_type)
            log.info(
                "OpenAPI patched with discriminated union for %d kinds",
                len(models),
            )
        else:
            log.warning("Kind registry empty or no valid schemas; OpenAPI remains generic")
    except Exception as e:
        log.exception("Failed to build OpenAPI typing bridge: %s", e)

    yield
    log.info("Artifact service shutdown complete")


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(CorrelationIdMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*", "x-request-id", "x-correlation-id"],
    expose_headers=["x-request-id", "x-correlation-id"],
)

app.include_router(registry_router)
app.include_router(category_router)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
