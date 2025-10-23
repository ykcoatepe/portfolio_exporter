from __future__ import annotations

import asyncio
import threading

import anyio

from psd.web.sse import SseManager


def test_sse_broadcast_cross_thread() -> None:
    manager = SseManager()

    async def _collect() -> str:
        queue = manager.subscribe()

        def _sender() -> None:
            manager.broadcast("ping", {"ok": True})

        thread = threading.Thread(target=_sender)
        thread.start()
        thread.join(timeout=2)

        return await asyncio.wait_for(queue.get(), timeout=2)

    message = anyio.run(_collect)
    assert "event: ping" in message
    assert '"ok":true' in message
