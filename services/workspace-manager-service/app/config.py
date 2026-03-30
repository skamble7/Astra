# services/workspace-manager-service/app/config.py
import os
from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str = "ASTRA Workspace Manager Service"
    host: str = "0.0.0.0"
    port: int = 9027

    # Mongo
    mongo_uri: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_db: str = os.getenv("MONGO_DB", "astra")

    # RabbitMQ
    rabbitmq_uri: str = os.getenv("RABBITMQ_URI", "amqp://raina:raina@localhost:5672/")
    rabbitmq_exchange: str = os.getenv("RABBITMQ_EXCHANGE", "raina.events")

    # Events: org/tenant segment for versioned routing keys
    events_org: str = os.getenv("EVENTS_ORG", "astra")
    platform_events_org: str = os.getenv("PLATFORM_EVENTS_ORG", "platform")

    # Durable named queue for workspace events consumer
    consumer_queue_workspace: str = os.getenv("CONSUMER_QUEUE_WORKSPACE", "platform.workspace.v1")

    # Upstream artifact-service (registry reads for schema validation)
    artifact_svc_base_url: str = os.getenv("ARTIFACT_SVC_BASE_URL", "http://astra-artifact-service:9020")


settings = Settings()
