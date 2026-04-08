"""
Minimal Protocol definitions for external dependencies used by conductor-core nodes.

These allow execution nodes to remain decoupled from service-specific implementations
(RunRepository, ArtifactServiceClient, EventPublisher). Any object whose methods
structurally match these protocols can be passed to the node factories.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol


class RunRepositoryProtocol(Protocol):
    async def step_failed(self, run_id: Any, step_id: str, *, error: str) -> None: ...
    async def step_completed(self, run_id: Any, step_id: str, *, metrics: Dict[str, Any]) -> None: ...
    async def step_skipped(self, run_id: Any, step_id: str, *, reason: str) -> None: ...
    async def step_started(self, run_id: Any, step_id: str) -> None: ...
    async def init_steps(self, run_id: Any, steps: List[Any]) -> None: ...
    async def append_tool_call_audit(self, run_id: Any, step_id: Optional[str], audit: Any) -> None: ...
    async def append_step_audit(self, run_id: Any, audit: Any) -> None: ...
    async def finalize_run(
        self,
        run_id: Any,
        *,
        run_artifacts: Any,
        status: Any,
        diffs_by_kind: Any,
        deltas: Any,
        run_summary_updates: Any,
    ) -> None: ...


class ArtifactServiceClientProtocol(Protocol):
    async def get_kind(self, kind_id: str, *, correlation_id: Optional[str] = None) -> Any: ...
    async def get_kind_schema(
        self, kind_id: str, version: str, *, correlation_id: Optional[str] = None
    ) -> Any: ...


class WorkspaceManagerClientProtocol(Protocol):
    async def upsert_batch(self, *, workspace_id: Any, items: Any, run_id: str) -> Any: ...


class EventPublisherProtocol(Protocol):
    async def publish_once(
        self,
        *,
        runs_repo: Any,
        run_id: Any,
        event: str,
        payload: Dict[str, Any],
        workspace_id: Optional[str] = None,
        playbook_id: Optional[str] = None,
        step_id: Optional[str] = None,
        phase: Optional[str] = None,
        strategy: Optional[str] = None,
        emitter: Optional[str] = None,
        correlation_id: Optional[str] = None,
        version: str = "v1",
    ) -> bool: ...
