# services/planner-service/app/events/capability_consumer.py
"""
RabbitMQ consumer for capability lifecycle events.

Binds to:
  <org>.capability.created.v1
  <org>.capability.updated.v1
  <org>.capability.deleted.v1

Keeps the ManifestCache in sync so the planner agent always works
with current capability definitions without requiring a service restart.
"""
from __future__ import annotations

import asyncio
import json
import logging

import aio_pika

from app.config import settings
from app.cache.manifest_cache import get_manifest_cache
from libs.astra_common.events import rk, Service

log = logging.getLogger("app.events.capability_consumer")

_RK_CREATED = rk(settings.events_org, Service.CAPABILITY, "created")
_RK_UPDATED = rk(settings.events_org, Service.CAPABILITY, "updated")
_RK_DELETED = rk(settings.events_org, Service.CAPABILITY, "deleted")


def _extract_cap_id(payload: dict) -> str:
    """
    Capability events carry the id at the top level: {"id": "...", ...}
    Raises ValueError if missing.
    """
    cap_id = payload.get("id") or payload.get("_id")
    if not cap_id:
        raise ValueError(f"capability payload missing 'id': {payload}")
    return str(cap_id)


async def _handle_created(payload: dict) -> None:
    cap_id = _extract_cap_id(payload)
    await get_manifest_cache().refresh_one(cap_id)
    log.info("[cap_consumer] created → refreshed cap_id=%s", cap_id)


async def _handle_updated(payload: dict) -> None:
    cap_id = _extract_cap_id(payload)
    await get_manifest_cache().refresh_one(cap_id)
    log.info("[cap_consumer] updated → refreshed cap_id=%s", cap_id)


async def _handle_deleted(payload: dict) -> None:
    cap_id = _extract_cap_id(payload)
    await get_manifest_cache().invalidate(cap_id)
    log.info("[cap_consumer] deleted → invalidated cap_id=%s", cap_id)


async def run_capability_consumer(shutdown_event: asyncio.Event) -> None:
    """
    Long-running consumer task. Re-connects on failure.
    Pass a shutdown_event to stop gracefully.
    """
    queue_name = settings.consumer_queue_capability

    while not shutdown_event.is_set():
        try:
            log.info("[cap_consumer] connecting to RabbitMQ ...")
            connection = await aio_pika.connect_robust(settings.rabbitmq_uri)

            async with connection:
                channel = await connection.channel()
                await channel.set_qos(prefetch_count=16)

                exchange = await channel.declare_exchange(
                    settings.rabbitmq_exchange,
                    aio_pika.ExchangeType.TOPIC,
                    durable=True,
                )
                queue = await channel.declare_queue(
                    queue_name or "",
                    durable=bool(queue_name),
                    auto_delete=not bool(queue_name),
                )

                await queue.bind(exchange, routing_key=_RK_CREATED)
                await queue.bind(exchange, routing_key=_RK_UPDATED)
                await queue.bind(exchange, routing_key=_RK_DELETED)

                log.info(
                    "[cap_consumer] consuming queue=%s exchange=%s rks=[%s, %s, %s]",
                    queue.name,
                    settings.rabbitmq_exchange,
                    _RK_CREATED,
                    _RK_UPDATED,
                    _RK_DELETED,
                )

                async with queue.iterator() as q:
                    async for message in q:
                        if shutdown_event.is_set():
                            break
                        async with message.process(requeue=False):
                            try:
                                payload = json.loads(message.body.decode("utf-8"))
                            except Exception:
                                log.exception("[cap_consumer] invalid JSON; dropping")
                                continue

                            try:
                                rk_str = message.routing_key
                                if rk_str == _RK_CREATED:
                                    await _handle_created(payload)
                                elif rk_str == _RK_UPDATED:
                                    await _handle_updated(payload)
                                elif rk_str == _RK_DELETED:
                                    await _handle_deleted(payload)
                                else:
                                    log.warning("[cap_consumer] unhandled rk=%s", rk_str)
                            except Exception:
                                log.exception("[cap_consumer] handler error (rk=%s); continuing", message.routing_key)

        except asyncio.CancelledError:
            break
        except Exception:
            log.exception("[cap_consumer] connection error; retrying in 3s")
            await asyncio.sleep(3.0)

    log.info("[cap_consumer] stopped")
