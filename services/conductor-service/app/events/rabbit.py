# services/conductor-service/app/events/rabbit.py
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
from libs.astra_common.events import rk, Service  # canonical RK helper

logger = logging.getLogger("app.events")

class RabbitBus:
    """
    Minimal async publisher using aio-pika, mirroring other services.
    """
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


# ─────────────────────────────────────────────────────────────
# EventPublisher (idempotent, adds headers)
# ─────────────────────────────────────────────────────────────

class EventPublisher:
    """
    Adds:
      - Standard headers
      - Idempotency via run doc flags (Mongo conditional update)
    """
    def __init__(self, *, bus: RabbitBus) -> None:
        self.bus = bus

    @staticmethod
    def _headers_base(
        *,
        run_id: str,
        workspace_id: Optional[str] = None,
        playbook_id: Optional[str] = None,
        step_id: Optional[str] = None,
        phase: Optional[str] = None,
        strategy: Optional[str] = None,
        emitter: Optional[str] = None,
        correlation_id: Optional[str] = None,
        idem_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        h: Dict[str, Any] = {
            "x-run-id": run_id,
        }
        if workspace_id: h["x-workspace-id"] = workspace_id
        if playbook_id: h["x-playbook-id"] = playbook_id
        if step_id: h["x-step-id"] = step_id
        if phase: h["x-phase"] = phase
        if strategy: h["x-strategy"] = strategy
        if emitter: h["x-emitter"] = emitter
        if correlation_id: h["x-correlation-id"] = correlation_id
        if idem_key: h["x-idempotency-key"] = idem_key
        h["x-at"] = datetime.now(timezone.utc).isoformat()
        return h

    @staticmethod
    def _idem_key(event: str, *, run_id: str, step_id: Optional[str] = None, phase: Optional[str] = None) -> str:
        # Examples:
        #   started -> "<run>:started"
        #   step.discovery_started -> "<run>:step.discovery_started:<step>"
        #   step.failed (discover)  -> "<run>:step.failed:<step>:discover"
        parts = [run_id, event]
        if step_id:
            parts.append(step_id)
        if phase:
            parts.append(phase)
        return ":".join(parts)

    async def publish_once(
        self,
        *,
        runs_repo,                        # RunRepository
        run_id: _UUID,
        event: str,                       # e.g. "started", "inputs.resolved", "step.discovery_started"
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
        """
        Atomically set a flag and publish only if we "won the race".
        Returns True if published, False if a duplicate.
        """
        idem_key = self._idem_key(event, run_id=str(run_id), step_id=step_id, phase=phase)
        flag_path = f"events.flags.{idem_key}"

        # atomic guard: only publish if our flag wasn't already set
        filt = {"run_id": str(run_id), flag_path: {"$ne": True}}
        upd = {"$set": {flag_path: True, "events.last": {"event": event, "at": datetime.now(timezone.utc)}}}
        try:
            res = await runs_repo._col.update_one(filt, upd)
            if getattr(res, "modified_count", 0) != 1:
                logger.debug("Event duplicate (skipped): %s", idem_key)
                return False
        except Exception:
            logger.warning("Event idempotency check failed for %s; proceeding best-effort", idem_key, exc_info=True)

        headers = self._headers_base(
            run_id=str(run_id),
            workspace_id=workspace_id,
            playbook_id=playbook_id,
            step_id=step_id,
            phase=phase,
            strategy=strategy,
            emitter=emitter,
            correlation_id=correlation_id,
            idem_key=idem_key,
        )

        await self.bus.publish(
            service=Service.CONDUCTOR.value,
            event=event,
            payload=payload,
            org=settings.events_org,
            headers=headers,
            version=version,
        )
        return True