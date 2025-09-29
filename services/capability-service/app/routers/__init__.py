# services/capability-service/app/routers/__init__.py
from .capability_router import router as capability_router
from .pack_router import router as pack_router
from .resolved_router import router as resolved_router
from .health_router import router as health_router

__all__ = ["capability_router", "pack_router", "resolved_router", "health_router"]