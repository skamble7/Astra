# services/planner-service/app/main.py
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

from app.config import settings
from app.infra.logging import setup_logging
from app.events.rabbit import get_bus, RabbitBus
from app.events.capability_consumer import run_capability_consumer
from app.db.mongodb import init_indexes, close_client as close_mongo_client
from app.cache.manifest_cache import get_manifest_cache
from app.api.routers import health_routes, session_routes, ws_routes

logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging(settings.service_name)
    logger.info("%s starting up", settings.service_name)

    # 1) RabbitMQ publisher connection
    bus: RabbitBus = get_bus()
    await bus.connect()
    logger.info("RabbitMQ connected (exchange=%s)", settings.rabbitmq_exchange)

    # 2) Mongo indexes
    await init_indexes()
    logger.info("Mongo indexes ensured (db=%s)", settings.mongo_db)

    # 3) Capability manifest cache warm-up
    try:
        cache = get_manifest_cache()
        await cache.refresh()
        logger.info("Capability manifest cache warmed up")
    except Exception:
        logger.warning("Capability manifest cache warm-up failed (non-fatal)", exc_info=True)

    # 4) Start capability consumer (keeps manifest cache in sync)
    shutdown_event = asyncio.Event()
    consumer_task = asyncio.create_task(
        run_capability_consumer(shutdown_event),
        name="capability-consumer",
    )
    logger.info(
        "Capability consumer started (queue=%s)", settings.consumer_queue_capability
    )

    try:
        yield
    finally:
        # Stop consumer first
        shutdown_event.set()
        try:
            await asyncio.wait_for(consumer_task, timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            consumer_task.cancel()
        logger.info("Capability consumer stopped")

        try:
            await bus.close()
            logger.info("RabbitMQ connection closed")
        except Exception:
            logger.warning("Error closing RabbitMQ", exc_info=True)

        try:
            await close_mongo_client()
            logger.info("Mongo client closed")
        except Exception:
            logger.warning("Error closing Mongo client", exc_info=True)

        logger.info("%s shutdown complete", settings.service_name)


app = FastAPI(
    title="Astra Planner Service",
    description="Intent-driven planning and execution agent for ASTRA capability packs",
    version="0.1.0",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)

app.include_router(health_routes.router)
app.include_router(session_routes.router)
app.include_router(ws_routes.router)
