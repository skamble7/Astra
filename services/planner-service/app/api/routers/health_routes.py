# services/planner-service/app/api/routers/health_routes.py
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter

from app.cache.manifest_cache import get_manifest_cache
from app.config import settings
from app.events.rabbit import get_bus

logger = logging.getLogger("app.api.health")

router = APIRouter(tags=["meta"])


@router.get("/", summary="Root metadata")
def root() -> Dict[str, Any]:
    return {
        "service": settings.service_name,
        "status": "ok",
        "message": "astra planner-service",
        "docs": "/docs",
        "health": "/health",
        "ready": "/ready",
        "version": "/version",
    }


@router.get("/health", summary="Liveness probe")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": settings.service_name,
        "at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ready", summary="Readiness probe")
async def ready() -> Dict[str, Any]:
    bus = get_bus()
    await bus.connect()
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


@router.post("/admin/cache/refresh", summary="Force reload all capabilities from capability-service")
async def refresh_capability_cache() -> Dict[str, Any]:
    cache = get_manifest_cache()
    await cache.refresh()
    from app.cache.manifest_cache import _memory_cache
    return {
        "status": "ok",
        "capabilities_loaded": len(_memory_cache),
        "at": datetime.now(timezone.utc).isoformat(),
    }
