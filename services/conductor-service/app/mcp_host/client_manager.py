# services/conductor-service/app/mcp_host/client_manager.py
from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from typing import Awaitable, Callable, Dict, Generic, Optional, TypeVar, Tuple, List

from app.mcp_host.types import ClientSignature

logger = logging.getLogger("app.mcp.manager")

T = TypeVar("T")


class _LRU(Generic[T]):
    def __init__(self, capacity: int = 32) -> None:
        self.capacity = capacity
        self._map: "OrderedDict[str, T]" = OrderedDict()

    def get(self, key: str) -> Optional[T]:
        if key not in self._map:
            return None
        val = self._map.pop(key)
        self._map[key] = val
        return val

    def put(self, key: str, val: T) -> None:
        if key in self._map:
            self._map.pop(key)
        elif len(self._map) >= self.capacity:
            self._map.popitem(last=False)  # evict LRU
        self._map[key] = val

    def items(self):
        return list(self._map.items())

    def pop(self, key: str) -> Optional[T]:
        return self._map.pop(key, None)

    def clear(self) -> None:
        self._map.clear()


class ClientManager(Generic[T]):
    """
    Persistent per-server client manager keyed by a signature string.
    Provides simple LRU + idle timeout eviction, and explicit shutdown.
    """

    def __init__(self, *, capacity: int = 32, idle_ttl_sec: int = 900) -> None:
        self.capacity = capacity
        self.idle_ttl_sec = idle_ttl_sec
        self._lru: _LRU[tuple[T, float]] = _LRU(capacity=capacity)
        self._lock = asyncio.Lock()

    async def get(self, signature: ClientSignature, factory: Callable[[], Awaitable[T]]) -> T:
        now = time.time()
        async with self._lock:
            hit = self._lru.get(signature)
            if hit:
                client, _last = hit
                self._lru.put(signature, (client, now))
                return client

            client = await factory()
            self._lru.put(signature, (client, now))
            logger.info("MCP client created for signature=%s", signature)
            return client

    async def shutdown(self, *, closer: Callable[[T], Awaitable[None]]) -> None:
        async with self._lock:
            items = self._lru.items()
            self._lru.clear()
        for sig, (client, _ts) in items:
            try:
                await closer(client)
                logger.info("MCP client closed signature=%s", sig)
            except Exception:
                logger.warning("Error closing client signature=%s", sig, exc_info=True)

    async def sweep_idle(self, *, closer: Callable[[T], Awaitable[None]]) -> None:
        now = time.time()
        to_close: List[Tuple[str, T]] = []
        async with self._lock:
            for sig, (client, ts) in list(self._lru.items()):
                if now - ts >= self.idle_ttl_sec:
                    self._lru.pop(sig)
                    to_close.append((sig, client))

        for sig, client in to_close:
            try:
                await closer(client)
                logger.info("MCP client (idle) closed signature=%s", sig)
            except Exception:
                logger.debug("Error closing idle client %s", sig, exc_info=True)