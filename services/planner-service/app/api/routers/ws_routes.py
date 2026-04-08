# services/planner-service/app/api/routers/ws_routes.py
"""
WebSocket endpoint for real-time session event streaming.

Client protocol:
  - Connect: GET /ws/sessions/{session_id}
  - Optional resume: first message { "type": "resume", "cursor": N }
  - Server sends: JSON event objects with { "idx": N, "type": ..., ... }
  - Client ping: { "type": "ping" } → server responds { "type": "pong" }
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.events.stream import get_stream

router = APIRouter(prefix="/ws", tags=["websocket"])
logger = logging.getLogger("app.api.ws")

_SEND_TIMEOUT = 30.0  # seconds


@router.websocket("/sessions/{session_id}")
async def session_websocket(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    logger.info("[ws] client connected session=%s", session_id)

    stream = get_stream(session_id)
    cursor = 0

    # Check for optional resume message (timeout 2s)
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=2.0)
        msg = json.loads(raw)
        if msg.get("type") == "resume":
            cursor = int(msg.get("cursor", 0))
            logger.info("[ws] resume session=%s cursor=%d", session_id, cursor)
    except (asyncio.TimeoutError, Exception):
        pass  # no resume message; start from beginning or given cursor

    queue = stream.subscribe(cursor=cursor, max_queue=1024)
    try:
        while True:
            # Wait for next event or client message (poll with timeout)
            try:
                event = await asyncio.wait_for(queue.get(), timeout=_SEND_TIMEOUT)
                await websocket.send_text(json.dumps(event))
            except asyncio.TimeoutError:
                # Send keepalive
                try:
                    await websocket.send_text(json.dumps({"type": "keepalive"}))
                except Exception:
                    break
            except Exception:
                break

            # Non-blocking check for client messages (ping/pong)
            try:
                client_msg = await asyncio.wait_for(websocket.receive_text(), timeout=0.01)
                parsed = json.loads(client_msg)
                if parsed.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except (asyncio.TimeoutError, Exception):
                pass

    except WebSocketDisconnect:
        logger.info("[ws] client disconnected session=%s", session_id)
    except Exception:
        logger.exception("[ws] error session=%s", session_id)
    finally:
        stream.unsubscribe(queue)
        logger.info("[ws] cleanup done session=%s", session_id)
