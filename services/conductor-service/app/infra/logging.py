# services/conductor-service/app/infra/logging.py
from __future__ import annotations
import logging
import os
from typing import Literal

_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
_LEVELS: dict[str, int] = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}

def setup_logging(service_name: str = "conductor-service") -> None:
    """
    Minimal, consistent structured-ish logging across services.
    """
    level = _LEVELS.get(_LOG_LEVEL, logging.INFO)
    logging.basicConfig(
        level=level,
        format=(
            "%(asctime)s | %(levelname)s | %(name)s | "
            f"svc={service_name} | %(message)s"
        ),
    )
    # quiet noisy deps if needed
    logging.getLogger("aio_pika").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(level)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)