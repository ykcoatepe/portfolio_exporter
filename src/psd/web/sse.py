from __future__ import annotations

import asyncio
import json
import threading
from asyncio import QueueEmpty
from collections.abc import AsyncIterator
from typing import Any

from fastapi import Request
from fastapi.responses import StreamingResponse

_DEFAULT_QUEUE_SIZE = 16


class SseManager:
    """Lightweight SSE broadcaster using per-subscriber asyncio queues."""

    def __init__(
        self,
        *,
        heartbeat_interval: int = 15,
        queue_size: int = _DEFAULT_QUEUE_SIZE,
    ) -> None:
        self._heartbeat_interval = max(1, int(heartbeat_interval))
        self._queue_size = max(1, int(queue_size))
        self._queues: set[asyncio.Queue[str]] = set()
        self._event_id = 0
        self._lock = threading.Lock()

    @property
    def heartbeat_interval(self) -> int:
        return self._heartbeat_interval

    def subscribe(self) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=self._queue_size)
        with self._lock:
            self._queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        with self._lock:
            self._queues.discard(queue)

    def broadcast(self, event_type: str, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            raise TypeError("SSE payload must be a dictionary")
        with self._lock:
            self._event_id += 1
            event_id = self._event_id
            queues = list(self._queues)

        message = _format_event(event_id, event_type, payload)
        for queue in queues:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                try:
                    _ = queue.get_nowait()
                except QueueEmpty:
                    pass
                try:
                    queue.put_nowait(message)
                except asyncio.QueueFull:
                    self.unsubscribe(queue)

    def heartbeat_message(self) -> str:
        return "event: heartbeat\ndata: {}\n\n"


def _format_event(event_id: int, event_type: str, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    parts = [f"id: {event_id}", f"event: {event_type}", f"data: {body}", ""]
    return "\n".join(parts) + "\n"


async def _iter_sse_messages(
    request: Request,
    manager: SseManager,
    *,
    close_after_event: bool = False,
) -> AsyncIterator[str]:
    queue = manager.subscribe()
    try:
        heartbeat = manager.heartbeat_interval
        yield manager.heartbeat_message()
        while True:
            if await request.is_disconnected():
                break
            try:
                message = await asyncio.wait_for(queue.get(), timeout=heartbeat)
                yield message
                if close_after_event and "event: heartbeat" not in message:
                    break
            except TimeoutError:
                yield manager.heartbeat_message()
    finally:
        manager.unsubscribe(queue)


async def sse_endpoint(request: Request, manager: SseManager) -> StreamingResponse:
    """Return a streaming response suitable for EventSource clients."""
    close_after_event = request.query_params.get("test_once") == "1"
    generator = _iter_sse_messages(
        request, manager, close_after_event=close_after_event
    )
    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(generator, media_type="text/event-stream", headers=headers)
