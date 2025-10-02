# services/conductor-service/app/main.py
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

from app.config import settings
from app.infra.logging import setup_logging
from app.events.rabbit import get_bus, RabbitBus
from app.db.mongodb import init_indexes, close_client as close_mongo_client
from app.mcp_host import mcp_client_manager  # no-op unless pooling is enabled
from app.api.routers import health_routes
from app.api.routers import runs_routes

logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    App lifespan:
      - configure logging
      - connect event bus (RabbitMQ)
      - init Mongo indexes
      - graceful shutdown: bus, MCP client pool, Mongo client
    """
    setup_logging(settings.service_name)
    logger.info("%s starting up", settings.service_name)

    # 1) RabbitMQ
    bus: RabbitBus = get_bus()
    await bus.connect()
    logger.info("RabbitMQ connected (exchange=%s)", settings.rabbitmq_exchange)

    # 2) Mongo indexes
    await init_indexes()
    logger.info("Mongo indexes ensured (db=%s)", settings.mongo_db)

    try:
        yield
    finally:
        # a) Event bus
        try:
            await bus.close()
            logger.info("RabbitMQ connection closed")
        except Exception:
            logger.warning("Error closing RabbitMQ", exc_info=True)

        # b) MCP client pool
        try:
            await mcp_client_manager.shutdown(closer=lambda c: c.close())
            logger.info("MCP client pool shutdown complete")
        except Exception:
            logger.warning("Error shutting down MCP client pool", exc_info=True)

        # c) Mongo client
        try:
            await close_mongo_client()
            logger.info("Mongo client closed")
        except Exception:
            logger.warning("Error closing Mongo client", exc_info=True)

        logger.info("%s shutdown complete", settings.service_name)


app = FastAPI(
    title="Astra Conductor Service",
    description="MCP host + playbook runner for capability packs",
    version="0.1.0",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)

app.include_router(health_routes.router)
app.include_router(runs_routes.router)