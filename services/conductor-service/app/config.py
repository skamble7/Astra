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
    workspace_mgr_base_url: str = os.getenv(
        "WORKSPACE_MGR_BASE_URL", "http://astra-workspace-manager-service:9027"
    )

    # HTTP client
    http_client_timeout_seconds: float = float(
        os.getenv("HTTP_CLIENT_TIMEOUT_SECONDS", "30")
    )

    # Identity
    service_name: str = os.getenv("SERVICE_NAME", "conductor-service")

    # ConfigForge: canonical ref for the conductor's agent LLM.
    # Also used as the fallback when OVERRIDE_CAPABILITY_LLM=1.
    # CONFIG_FORGE_URL is read directly from env by polyllm's RemoteConfigLoader.
    conductor_llm_config_ref: str = os.getenv("CONDUCTOR_LLM_CONFIG_REF", "")

    # LLM Override: When true, all capabilities use conductor_llm_config_ref
    override_capability_llm: bool = bool(int(os.getenv("OVERRIDE_CAPABILITY_LLM", "0")))

    # Skip enrichment nodes (saves time and cost during testing)
    skip_diagram: bool = bool(int(os.getenv("SKIP_DIAGRAM", "0")))
    skip_narrative: bool = bool(int(os.getenv("SKIP_NARRATION", "0")))

    model_config = SettingsConfigDict(env_file=None, extra="ignore")


settings = Settings()