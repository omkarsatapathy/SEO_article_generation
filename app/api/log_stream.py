"""
Real-time log streaming via Server-Sent Events.

Installs a custom logging handler at import time that captures every log
record emitted anywhere in the process and fans them out to all connected
SSE clients.  Thread-safe: uses asyncio.AbstractEventLoop.call_soon_threadsafe
so records emitted from sync threads (e.g. LangGraph internals) are safely
delivered to the async queues.
"""

import asyncio
import json
import logging
from collections import deque
from typing import List

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/logs", tags=["logs"])

# ── Shared state ──────────────────────────────────────────────────────────────

_buffer: deque = deque(maxlen=400)          # ring-buffer of recent entries
_queues: List[asyncio.Queue] = []           # one queue per connected client
_event_loop: asyncio.AbstractEventLoop | None = None


# ── Broadcast helpers ─────────────────────────────────────────────────────────

def _push_to_queues(entry: dict) -> None:
    """Must be called from inside the event loop."""
    for q in list(_queues):
        try:
            q.put_nowait(entry)
        except asyncio.QueueFull:
            pass


# ── Custom log handler ────────────────────────────────────────────────────────

class _BroadcastHandler(logging.Handler):
    """Captures every log record and pushes it to connected SSE clients."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            text = self.format(record)
        except Exception:
            text = record.getMessage()

        entry = {
            "level": record.levelname,
            "name": record.name,
            "text": text,
        }
        _buffer.append(entry)

        loop = _event_loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(_push_to_queues, entry)


_handler = _BroadcastHandler()
_handler.setFormatter(
    logging.Formatter(
        "%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
        datefmt="%H:%M:%S",
    )
)
# Attach to root logger so every logger in the process is captured.
logging.getLogger().addHandler(_handler)


# ── SSE endpoint ──────────────────────────────────────────────────────────────

@router.get("/stream")
async def stream_logs():
    """
    Server-Sent Events endpoint.
    Sends buffered history on connect, then streams live records.
    """
    global _event_loop
    _event_loop = asyncio.get_event_loop()

    q: asyncio.Queue = asyncio.Queue(maxsize=400)
    _queues.append(q)

    async def _gen():
        # Replay buffer so the client sees recent history immediately.
        for entry in list(_buffer):
            yield f"data: {json.dumps(entry)}\n\n"

        try:
            while True:
                try:
                    entry = await asyncio.wait_for(q.get(), timeout=20)
                    yield f"data: {json.dumps(entry)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            try:
                _queues.remove(q)
            except ValueError:
                pass

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
