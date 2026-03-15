# services/planner-service/app/cache/manifest_cache.py
"""
Capability manifest cache backed by Redis (with in-memory fallback).

On startup: fetch all capabilities from capability-service → store in Redis with TTL.
On RabbitMQ event (capability.updated / capability.created): refresh entry.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from app.config import settings
from app.clients.capability_service import CapabilityServiceClient

logger = logging.getLogger("app.cache.manifest_cache")

# In-memory fallback
_memory_cache: Dict[str, Dict[str, Any]] = {}
_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is None:
        try:
            import redis.asyncio as redis_lib
            _redis_client = redis_lib.from_url(settings.redis_url, decode_responses=True)
        except Exception as e:
            logger.warning("Redis unavailable (%s); using in-memory cache only", e)
    return _redis_client


_REDIS_PREFIX = "astra:planner:cap:"
_ALL_CAPS_KEY = "astra:planner:all_caps"


class ManifestCache:
    """
    Caches capability manifests. Redis is primary; in-memory is fallback.
    """

    def __init__(self) -> None:
        self._cap_client = CapabilityServiceClient()

    async def refresh(self) -> None:
        """Fetch all capabilities from capability-service and populate cache."""
        try:
            caps = await self._cap_client.list_capabilities()
            logger.info("ManifestCache.refresh: fetched %d capabilities", len(caps))
        except Exception as e:
            logger.warning("ManifestCache.refresh: capability-service unavailable (%s)", e)
            return

        # Update in-memory
        _memory_cache.clear()
        for cap in caps:
            cap_id = cap.get("id")
            if cap_id:
                _memory_cache[cap_id] = cap

        # Update Redis (non-fatal)
        redis = _get_redis()
        if redis:
            try:
                ttl = settings.manifest_cache_ttl_seconds
                # Store all IDs list
                all_ids = list(_memory_cache.keys())
                await redis.setex(_ALL_CAPS_KEY, ttl, json.dumps(all_ids))
                # Store each capability
                for cap_id, cap in _memory_cache.items():
                    await redis.setex(f"{_REDIS_PREFIX}{cap_id}", ttl, json.dumps(cap))
                logger.info("ManifestCache.refresh: stored %d capabilities in Redis", len(all_ids))
            except Exception as e:
                logger.warning("ManifestCache.refresh: Redis write failed (%s)", e)

    async def get_capability(self, cap_id: str) -> Optional[Dict[str, Any]]:
        # 1. In-memory
        if cap_id in _memory_cache:
            return _memory_cache[cap_id]

        # 2. Redis
        redis = _get_redis()
        if redis:
            try:
                val = await redis.get(f"{_REDIS_PREFIX}{cap_id}")
                if val:
                    cap = json.loads(val)
                    _memory_cache[cap_id] = cap
                    return cap
            except Exception as e:
                logger.debug("ManifestCache.get_capability: Redis read failed (%s)", e)

        # 3. Direct capability-service call
        try:
            cap = await self._cap_client.get_capability(cap_id)
            if cap:
                _memory_cache[cap_id] = cap
            return cap
        except Exception as e:
            logger.warning("ManifestCache.get_capability: fallback fetch failed for %s: %s", cap_id, e)
            return None

    async def get_all_capabilities(self) -> List[Dict[str, Any]]:
        # 1. In-memory (if populated)
        if _memory_cache:
            return list(_memory_cache.values())

        # 2. Redis
        redis = _get_redis()
        if redis:
            try:
                ids_raw = await redis.get(_ALL_CAPS_KEY)
                if ids_raw:
                    all_ids = json.loads(ids_raw)
                    caps = []
                    for cap_id in all_ids:
                        val = await redis.get(f"{_REDIS_PREFIX}{cap_id}")
                        if val:
                            cap = json.loads(val)
                            _memory_cache[cap_id] = cap
                            caps.append(cap)
                    if caps:
                        return caps
            except Exception as e:
                logger.debug("ManifestCache.get_all: Redis read failed (%s)", e)

        # 3. Refresh from capability-service
        await self.refresh()
        return list(_memory_cache.values())

    async def invalidate(self, cap_id: str) -> None:
        _memory_cache.pop(cap_id, None)
        redis = _get_redis()
        if redis:
            try:
                await redis.delete(f"{_REDIS_PREFIX}{cap_id}")
            except Exception:
                pass

    async def refresh_one(self, cap_id: str) -> Optional[Dict[str, Any]]:
        """Refresh a single capability from capability-service."""
        _memory_cache.pop(cap_id, None)
        return await self.get_capability(cap_id)


_cache_instance: Optional[ManifestCache] = None


def get_manifest_cache() -> ManifestCache:
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = ManifestCache()
    return _cache_instance
