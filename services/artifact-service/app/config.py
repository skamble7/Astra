# services/artifact-service/app/config.py
import os
from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str = "astra Artifact Service"
    host: str = "0.0.0.0"
    port: int = 8011

    # Mongo
    mongo_uri: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_db: str = os.getenv("MONGO_DB", "astra")


settings = Settings()
