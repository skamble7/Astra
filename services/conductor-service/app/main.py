# services/conductor-service/app/main.py
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator, Dict, Any

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

from app.config import settings
from app.infra.logging import setup_logging
from app.events.rabbit import get_bus, RabbitBus


logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    App lifespan:
      - configure logging
      - connect event bus (RabbitMQ)
      - (future) warm up db, http clients, etc.
    """
    setup_logging(settings.service_name)
    logger.info("%s starting up", settings.service_name)

    # Connect Rabbit (shared exchange raina.events)
    bus: RabbitBus = get_bus()
    await bus.connect()

    try:
        yield
    finally:
        # Graceful shutdown
        await bus.close()
        logger.info("%s shutdown complete", settings.service_name)


app = FastAPI(
    title="Astra Conductor Service",
    description="MCP host + playbook runner for capability packs",
    version="0.1.0",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)


# --- Health Endpoints ------------------------------------------------------- #

@app.get("/", tags=["meta"])
def root() -> Dict[str, Any]:
    return {
        "service": settings.service_name,
        "status": "ok",
        "message": "astra conductor-service",
        "docs": "/docs",
        "health": "/health",
        "ready": "/ready",
        "version": "/version",
    }


@app.get("/health", tags=["meta"])
def health() -> Dict[str, Any]:
    """
    Liveness probe: process is up and app is constructed.
    """
    return {
        "status": "ok",
        "service": settings.service_name,
        "at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["meta"])
async def ready() -> Dict[str, Any]:
    """
    Readiness probe: verify essential dependencies we already initialize here.
    For now, we check the RabbitMQ exchange is reachable.
    """
    # Ensure the bus is connected (lifespan already connects; this is a light check)
    bus = get_bus()
    await bus.connect()  # no-op if already connected
    return {
        "status": "ready",
        "service": settings.service_name,
        "exchange": settings.rabbitmq_exchange,
        "at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/version", tags=["meta"])
def version() -> Dict[str, Any]:
    return {
        "service": settings.service_name,
        "version": app.version,
    }