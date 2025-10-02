# services/conductor-service/app/mcp_host/__init__.py
from __future__ import annotations

# re-export for convenience (only modules that actually exist)
from .types import (
    TransportKind,
    ClientSignature,
    DiscoveryReport,
    ToolCallSpec,
    InvokePage,
    InvokeResult,
)

from .client_manager import ClientManager  # if you decide to pool again
from .client_manager import ClientManager as _CM

# a tiny, shared manager instance for future pooling (kept for compatibility)
mcp_client_manager = _CM(capacity=16, idle_ttl_sec=900)

__all__ = [
    "TransportKind",
    "ClientSignature",
    "DiscoveryReport",
    "ToolCallSpec",
    "InvokePage",
    "InvokeResult",
    "ClientManager",
    "mcp_client_manager",
]