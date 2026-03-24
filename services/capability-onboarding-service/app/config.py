from __future__ import annotations
import os
from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str = "Astra Capability Onboarding Service"
    host: str = "0.0.0.0"
    port: int = 9026

    # Downstream services
    capability_svc_base_url: str = os.getenv(
        "CAPABILITY_SVC_BASE_URL", "http://astra-capability-service:9021"
    )
    artifact_svc_base_url: str = os.getenv(
        "ARTIFACT_SVC_BASE_URL", "http://astra-artifact-service:9020"
    )

    http_client_timeout_seconds: float = float(
        os.getenv("HTTP_CLIENT_TIMEOUT_SECONDS", "30")
    )

    service_name: str = os.getenv("SERVICE_NAME", "capability-onboarding-service")

    # ConfigForge — LLM configuration for metadata inference.
    # CONFIG_FORGE_URL is read directly from env by polyllm's RemoteConfigLoader.
    llm_config_ref: str = os.getenv("ONBOARDING_LLM_CONFIG_REF", "")

    # When running inside Docker, localhost in a user-supplied MCP URL resolves
    # to the container itself, not the host machine. Set this to
    # "host.docker.internal" in Docker so the service can reach host ports.
    mcp_localhost_alias: str = os.getenv("MCP_LOCALHOST_ALIAS", "")


settings = Settings()
