# services/workspace-manager-service/app/main.py
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .logging_conf import configure_logging
from .routers.artifact_routes import router as artifact_router
from .db.mongodb import get_db
from .dal import artifact_dal
from .events.workspace_consumer import run_workspace_created_consumer
from .config import settings
from .middleware.correlation import CorrelationIdMiddleware, CorrelationIdFilter

configure_logging()
log = logging.getLogger(__name__)

_corr_filter = CorrelationIdFilter()
for name in ("", "uvicorn.access", "uvicorn.error", __name__.split(".")[0] or "app"):
    logging.getLogger(name).addFilter(_corr_filter)

_shutdown_event: asyncio.Event | None = None
_consumer_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _shutdown_event, _consumer_task

    db = await get_db()

    await artifact_dal.ensure_indexes(db)
    log.info("Mongo indexes ensured for workspace artifacts")

    _shutdown_event = asyncio.Event()
    _consumer_task = asyncio.create_task(run_workspace_created_consumer(db, _shutdown_event))
    log.info("workspace consumer started")

    try:
        yield
    finally:
        if _shutdown_event:
            _shutdown_event.set()
        if _consumer_task:
            _consumer_task.cancel()
            try:
                await _consumer_task
            except Exception:
                pass
        log.info("Workspace manager service shutdown complete")


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(CorrelationIdMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*", "x-request-id", "x-correlation-id"],
    expose_headers=["x-request-id", "x-correlation-id"],
)

app.include_router(artifact_router)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
