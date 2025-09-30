from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from app.config import settings

logger = logging.getLogger("app.clients.http")


# One shared AsyncClient per base_url (connection pooling + timeouts)
_clients: dict[str, httpx.AsyncClient] = {}
_clients_lock = asyncio.Lock()


async def get_http_client(base_url: str) -> httpx.AsyncClient:
    async with _clients_lock:
        client = _clients.get(base_url)
        if client is None or client.is_closed:
            client = httpx.AsyncClient(
                base_url=base_url,
                timeout=settings.http_client_timeout_seconds,
                headers={
                    "Accept": "application/json",
                    "User-Agent": f"astra-conductor/{settings.service_name}",
                },
            )
            _clients[base_url] = client
            logger.info("HTTP client created for %s", base_url)
        return client


class ServiceClientError(RuntimeError):
    def __init__(self, *, service: str, status: int, url: str, body: str) -> None:
        super().__init__(f"{service} HTTP {status}: {url} :: {body[:500]}")
        self.service = service
        self.status = status
        self.url = url
        self.body = body


def _raise_for_status(service: str, resp: httpx.Response) -> None:
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        # keep body for debugging (limited)
        body = ""
        try:
            body = resp.text
        except Exception:
            pass
        raise ServiceClientError(service=service, status=resp.status_code, url=str(resp.request.url), body=body) from e


# A conservative retry wrapper for idempotent GETs only
def retryable_get(fn):
    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=0.2, max=2.0),
        reraise=True,
    )(fn)