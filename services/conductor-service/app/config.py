# services/conductor-service/app/config.py
from __future__ import annotations
import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Mongo
    mongo_uri: str = os.getenv("MONGO_URI", "")
    mongo_db: str = os.getenv("MONGO_DB", "astra")

    # RabbitMQ
    rabbitmq_uri: str = os.getenv(
        "RABBITMQ_URI", "amqp://raina:raina@host.docker.internal:5672/"
    )
    rabbitmq_exchange: str = os.getenv("RABBITMQ_EXCHANGE", "raina.events")
    events_org: str = os.getenv("EVENTS_ORG", "astra")
    platform_events_org: str = os.getenv("PLATFORM_EVENTS_ORG", "platform")

    # Downstream services
    capability_svc_base_url: str = os.getenv(
        "CAPABILITY_SVC_BASE_URL", "http://astra-capability-service:9021"
    )
    artifact_svc_base_url: str = os.getenv(
        "ARTIFACT_SVC_BASE_URL", "http://astra-artifact-service:9020"
    )

    # HTTP client
    http_client_timeout_seconds: float = float(
        os.getenv("HTTP_CLIENT_TIMEOUT_SECONDS", "30")
    )

    # Identity
    service_name: str = os.getenv("SERVICE_NAME", "conductor-service")

    # LLM (Agent driver)
    llm_provider: str = os.getenv("LLM_PROVIDER", "openai")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.1"))
    llm_max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "4000"))
    llm_strict_json: bool = bool(int(os.getenv("LLM_STRICT_JSON", "1")))

    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    # Secret resolution
    secret_backend: str = os.getenv("SECRET_BACKEND", "env")  # "env" | "vault" | "kms" | ...
    secret_alias_prefix: str = os.getenv("SECRET_ALIAS_PREFIX", "ASTRA_SECRET_")

    # Optional: future Vault/KMS configuration placeholders
    vault_addr: str = os.getenv("VAULT_ADDR", "")
    vault_token_env: str = os.getenv("VAULT_TOKEN_ENV", "VAULT_TOKEN")


settings = Settings()