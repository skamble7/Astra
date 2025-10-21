# services/astraui-resolver-service/app/core/config.py
from __future__ import annotations

import os
from functools import lru_cache

def _as_bool(v: str | None, default: bool = False) -> bool:
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}

class Settings:
    # Service
    service_name: str = os.getenv("SERVICE_NAME", "astraui-resolver-service")
    app_port: int = int(os.getenv("APP_PORT", "9024"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # Mongo
    mongo_uri: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_db: str = os.getenv("MONGO_DB", "astra")

    # CORS (comma-separated origins; "*" allowed for dev)
    cors_allow_origins: str = os.getenv("CORS_ALLOW_ORIGINS", "*")

    # Seeding
    seed_on_start: bool = _as_bool(os.getenv("SEED_ON_START"), default=True)

@lru_cache(maxsize=1)
def _settings() -> Settings:
    return Settings()

settings = _settings()