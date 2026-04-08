# services/planner-service/app/config.py
from __future__ import annotations
import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # MongoDB
    mongo_uri: str = os.getenv("MONGO_URI", "")
    mongo_db: str = os.getenv("MONGO_DB", "astra")

    # Redis
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # RabbitMQ
    rabbitmq_uri: str = os.getenv("RABBITMQ_URI", "amqp://raina:raina@host.docker.internal:5672/")
    rabbitmq_exchange: str = os.getenv("RABBITMQ_EXCHANGE", "raina.events")
    events_org: str = os.getenv("EVENTS_ORG", "astra")
    platform_events_org: str = os.getenv("PLATFORM_EVENTS_ORG", "platform")

    # Downstream services
    capability_svc_base_url: str = os.getenv("CAPABILITY_SVC_BASE_URL", "http://astra-capability-service:9021")
    conductor_svc_base_url: str = os.getenv("CONDUCTOR_SVC_BASE_URL", "http://astra-conductor-service:9022")
    artifact_svc_base_url: str = os.getenv("ARTIFACT_SVC_BASE_URL", "http://astra-artifact-service:9020")
    workspace_mgr_base_url: str = os.getenv("WORKSPACE_MGR_BASE_URL", "http://astra-workspace-manager-service:9027")

    # HTTP client
    http_client_timeout_seconds: float = float(os.getenv("HTTP_CLIENT_TIMEOUT_SECONDS", "30"))

    # Identity
    service_name: str = os.getenv("SERVICE_NAME", "planner-service")
    service_version: str = os.getenv("SERVICE_VERSION", "0.1.0")

    # LLM: planner agent LLM config ref (ConfigForge)
    planner_llm_config_ref: str = os.getenv("PLANNER_LLM_CONFIG_REF", "")

    # Diagram MCP server — platform-level enrichment, always available independently of capability registry
    diagram_mcp_base_url: str = os.getenv("DIAGRAM_MCP_BASE_URL", "http://host.docker.internal:8001")
    diagram_mcp_path: str = os.getenv("DIAGRAM_MCP_PATH", "/mcp")
    diagram_mcp_timeout_sec: int = int(os.getenv("DIAGRAM_MCP_TIMEOUT_SEC", "120"))

    # Capability cache
    manifest_cache_ttl_seconds: int = int(os.getenv("MANIFEST_CACHE_TTL_SECONDS", "300"))

    # Consumer queues
    consumer_queue_capability: str = os.getenv("CONSUMER_QUEUE_CAPABILITY", "planner.capability.v1")

    # Skip enrichment nodes (saves time and cost during testing)
    skip_diagram: bool = bool(int(os.getenv("SKIP_DIAGRAM", "0")))
    skip_narrative: bool = bool(int(os.getenv("SKIP_NARRATION", "0")))

    model_config = SettingsConfigDict(env_file=None, extra="ignore")


settings = Settings()
