from __future__ import annotations

import json
import asyncio

from src.psd.web import server


def test_broadcast_delivers_to_sse_queue() -> None:
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1)
    server._sse_clients.add(queue)
    try:
        payload = {"snapshot": {"vix": 20}, "rows": []}
        server.broadcast(payload)
        data = queue.get_nowait()
    finally:
        server._sse_clients.discard(queue)
    parsed = json.loads(data)
    assert parsed["snapshot"]["vix"] == 20
