# services/planner-service/app/events/rabbit.py
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from uuid import UUID as _UUID

import aio_pika
from aio_pika import ExchangeType, Message

from app.config import settings
from libs.astra_common.events import rk, Service

logger = logging.getLogger("app.events")


class RabbitBus:
    def __init__(self) -> None:
        self._conn: Optional[aio_pika.RobustConnection] = None
        self._chan: Optional[aio_pika.abc.AbstractChannel] = None
        self._ex: Optional[aio_pika.abc.AbstractExchange] = None
        self._lock = asyncio.Lock()

    async def connect(self) -> "RabbitBus":
        async with self._lock:
            if self._conn and not self._conn.is_closed:
                return self
            logger.info("Rabbit: connecting...")
            self._conn = await aio_pika.connect_robust(settings.rabbitmq_uri)
            self._chan = await self._conn.channel(publisher_confirms=False)
            self._ex = await self._chan.declare_exchange(
                settings.rabbitmq_exchange, ExchangeType.TOPIC, durable=True
            )
            logger.info("Rabbit: connected; exchange declared (%s)", settings.rabbitmq_exchange)
        return self

    async def close(self) -> None:
        if self._conn and not self._conn.is_closed:
            await self._conn.close()
            logger.info("Rabbit: connection closed")

    async def publish(
        self,
        *,
        service: str,
        event: str,
        payload: dict,
        version: str = "v1",
        org: Optional[str] = None,
        headers: Optional[dict] = None,
    ) -> None:
        if not self._ex:
            await self.connect()
        routing_key = rk(org or settings.events_org, service, event, version)
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        message = Message(
            body=body,
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            content_type="application/json",
            headers=headers or {},
        )
        await self._ex.publish(message, routing_key=routing_key)
        logger.info("Rabbit: published %s (%d bytes)", routing_key, len(body))


_bus: Optional[RabbitBus] = None


def get_bus() -> RabbitBus:
    global _bus
    if _bus is None:
        _bus = RabbitBus()
    return _bus


class EventPublisher:
    """Idempotent event publisher for planner-service events."""

    def __init__(self, *, bus: RabbitBus) -> None:
        self.bus = bus

    async def publish_once(
        self,
        *,
        runs_repo,
        run_id: _UUID,
        event: str,
        payload: Dict[str, Any],
        workspace_id: Optional[str] = None,
        playbook_id: Optional[str] = None,
        step_id: Optional[str] = None,
        phase: Optional[str] = None,
        strategy: Optional[str] = None,
        emitter: Optional[str] = None,
        correlation_id: Optional[str] = None,
        version: str = "v1",
    ) -> bool:
        idem_key = ":".join(filter(None, [str(run_id), event, step_id, phase]))
        flag_path = f"events.flags.{idem_key}"

        filt = {"run_id": str(run_id), flag_path: {"$ne": True}}
        upd = {"$set": {flag_path: True, "events.last": {"event": event, "at": datetime.now(timezone.utc)}}}
        try:
            res = await runs_repo._col.update_one(filt, upd)
            if getattr(res, "modified_count", 0) != 1:
                logger.debug("Event duplicate (skipped): %s", idem_key)
                return False
        except Exception:
            logger.warning("Event idempotency check failed for %s; proceeding best-effort", idem_key, exc_info=True)

        headers: Dict[str, Any] = {
            "x-run-id": str(run_id),
            "x-at": datetime.now(timezone.utc).isoformat(),
        }
        if workspace_id:
            headers["x-workspace-id"] = workspace_id
        if playbook_id:
            headers["x-playbook-id"] = playbook_id
        if step_id:
            headers["x-step-id"] = step_id
        if emitter:
            headers["x-emitter"] = emitter
        if correlation_id:
            headers["x-correlation-id"] = correlation_id

        await self.bus.publish(
            service=Service.PLANNER.value,
            event=event,
            payload=payload,
            org=settings.events_org,
            headers=headers,
            version=version,
        )
        return True
