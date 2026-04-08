# services/planner-service/app/events/stream.py
"""
In-memory per-session event stream for WebSocket delivery.
Supports replay from a cursor (sequential event index).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("app.events.stream")

# Global registry: session_id → SessionStream
_streams: Dict[str, "SessionStream"] = {}


class SessionStream:
    """
    Manages event history and active subscriber queues for one session.
    Thread-safe for asyncio (single event loop).
    """

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._log: List[Dict[str, Any]] = []           # ordered event log
        self._queues: List[asyncio.Queue] = []          # active WebSocket subscriber queues

    def publish(self, event: Dict[str, Any]) -> None:
        """Append event to log and fan out to all active subscribers."""
        idx = len(self._log)
        record = {"idx": idx, **event}
        self._log.append(record)
        for q in list(self._queues):
            try:
                q.put_nowait(record)
            except asyncio.QueueFull:
                logger.warning("[stream] queue full for session=%s; dropping event idx=%d", self.session_id, idx)

    def subscribe(self, *, cursor: int = 0, max_queue: int = 256) -> asyncio.Queue:
        """
        Returns a queue pre-filled with events from `cursor` onwards.
        The caller must call `unsubscribe(q)` when done.
        """
        q: asyncio.Queue = asyncio.Queue(maxsize=max_queue)
        for record in self._log[cursor:]:
            try:
                q.put_nowait(record)
            except asyncio.QueueFull:
                break
        self._queues.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self._queues.remove(q)
        except ValueError:
            pass

    @property
    def event_count(self) -> int:
        return len(self._log)


def get_stream(session_id: str) -> SessionStream:
    if session_id not in _streams:
        _streams[session_id] = SessionStream(session_id)
    return _streams[session_id]


def publish_to_session(session_id: str, event: Dict[str, Any]) -> None:
    get_stream(session_id).publish(event)
