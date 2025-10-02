# services/conductor-service/app/mcp_host/types.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, TypedDict

TransportKind = Literal["http", "stdio"]
ClientSignature = str  # used by the client manager LRU

class DiscoveryReport(TypedDict, total=False):
    tools: List[str]
    resources: List[Any]
    prompts: List[Any]

class ToolCallSpec(TypedDict, total=False):
    tool: str
    args_schema: Dict[str, Any]
    timeout_sec: int
    retries: int
    expects_stream: bool
    cancellable: bool

class InvokePage(TypedDict, total=False):
    data: Dict[str, Any]
    cursor: Optional[str]

class InvokeResult(TypedDict, total=False):
    pages: List[InvokePage]
    stream: Optional[Any]
    metrics: Dict[str, Any]