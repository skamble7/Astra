from __future__ import annotations
import os
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Mongo
    mongo_uri: str = os.getenv("MONGO_URI", "")
    mongo_db: str = os.getenv("MONGO_DB", "astra")

    # RabbitMQ
    rabbitmq_uri: str = os.getenv("RABBITMQ_URI", "amqp://raina:raina@host.docker.internal:5672/")
    rabbitmq_exchange: str = os.getenv("RABBITMQ_EXCHANGE", "raina.events")
    events_org: str = os.getenv("EVENTS_ORG", "astra")
    platform_events_org: str = os.getenv("PLATFORM_EVENTS_ORG", "platform")

    # Downstream services
    capability_svc_base_url: str = os.getenv("CAPABILITY_SVC_BASE_URL", "http://astra-capability-service:9021")
    artifact_svc_base_url: str = os.getenv("ARTIFACT_SVC_BASE_URL", "http://astra-artifact-service:9020")

    # HTTP client
    http_client_timeout_seconds: float = float(os.getenv("HTTP_CLIENT_TIMEOUT_SECONDS", "30"))

    # Identity
    service_name: str = os.getenv("SERVICE_NAME", "conductor-service")

    model_config = SettingsConfigDict(env_file=None, extra="ignore")

settings = Settings()