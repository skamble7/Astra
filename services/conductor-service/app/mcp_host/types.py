# services/conductor-service/app/mcp_host/types.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, Iterable, Literal, Optional

TransportKind = Literal["http", "stdio"]
ClientSignature = str


@dataclass(frozen=True)
class ToolCallSpec:
    tool: str
    args_schema: Optional[Dict[str, Any]] = None
    output_kinds: Iterable[str] = field(default_factory=list)
    timeout_sec: int = 60
    retries: int = 1
    expects_stream: bool = False
    cancellable: bool = True


@dataclass
class DiscoveryReport:
    tools: list[str] = field(default_factory=list)
    resources: list[dict[str, Any]] = field(default_factory=list)
    prompts: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class InvokePage:
    data: Any
    cursor: Optional[str] = None


@dataclass
class InvokeResult:
    """If streaming, `stream` is set; else `pages` contains all pages."""
    pages: list[InvokePage] = field(default_factory=list)
    stream: Optional[AsyncIterator[InvokePage]] = None
    metrics: dict[str, Any] = field(default_factory=dict)