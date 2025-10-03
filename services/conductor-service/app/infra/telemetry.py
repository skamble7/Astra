# services/conductor-service/app/infra/telemetry.py
from __future__ import annotations
import time
from contextlib import contextmanager
from typing import Iterator

@contextmanager
def timer(metric_name: str) -> Iterator[None]:
    """
    Lightweight timing context manager; replace with real metrics later.
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        dur_ms = (time.perf_counter() - start) * 1000.0
        # Intentional no-op for now; caller can log dur_ms.
        # e.g., logger.info("metric", extra={"metric": metric_name, "ms": dur_ms})