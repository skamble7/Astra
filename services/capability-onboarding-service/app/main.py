from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.logging_conf import setup_logging
from app.middleware import add_cors, install_request_logging
from app.routers.health_router import router as health_router
from app.routers.llm_onboarding_router import router as llm_onboarding_router
from app.routers.mcp_onboarding_router import router as mcp_onboarding_router

logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("Starting %s on %s:%s", settings.app_name, settings.host, settings.port)
    yield
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.app_name,
    description="Backend for the MCP and LLM capability onboarding wizards.",
    lifespan=lifespan,
)

add_cors(app)
install_request_logging(app)

app.include_router(health_router)
app.include_router(mcp_onboarding_router)
app.include_router(llm_onboarding_router)


@app.get("/")
async def root():
    return {
        "service": settings.service_name,
        "name": settings.app_name,
        "status": "ok",
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    reload_flag = os.getenv("RELOAD", "0") in ("1", "true", "True")
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=reload_flag,
        log_level="info",
    )
