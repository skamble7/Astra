# services/conductor-service/app/api/routers/health_routes.py
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter

from app.config import settings
from app.events.rabbit import get_bus

logger = logging.getLogger("app.api.health")

router = APIRouter(tags=["meta"])


@router.get("/", summary="Root metadata")
def root() -> Dict[str, Any]:
    """
    Root landing with links and metadata.
    """
    return {
        "service": settings.service_name,
        "status": "ok",
        "message": "astra conductor-service",
        "docs": "/docs",
        "health": "/health",
        "ready": "/ready",
        "version": "/version",
    }


@router.get("/health", summary="Liveness probe")
def health() -> Dict[str, Any]:
    """
    Liveness probe: process is up and app is constructed.
    """
    return {
        "status": "ok",
        "service": settings.service_name,
        "at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ready", summary="Readiness probe")
async def ready() -> Dict[str, Any]:
    """
    Readiness probe: verifies essential dependencies are up.
    For now, we check RabbitMQ is connected.
    """
    bus = get_bus()
    await bus.connect()  # no-op if already connected
    return {
        "status": "ready",
        "service": settings.service_name,
        "exchange": settings.rabbitmq_exchange,
        "at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/version", summary="Service version")
def version() -> Dict[str, Any]:
    return {
        "service": settings.service_name,
        "version": settings.service_version,
    }