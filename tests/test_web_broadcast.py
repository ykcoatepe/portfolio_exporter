# SPDX-License-Identifier: MIT
from __future__ import annotations

import asyncio
import threading

from psd.web import server as public_server
from src.psd.web import server as impl_server


class _FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self._called = threading.Event()

    async def send_text(self, payload: str) -> None:  # pragma: no cover - exercised in loop
        self.messages.append(payload)
        self._called.set()

    async def close(self) -> None:  # pragma: no cover - not triggered in test
        pass

    def wait(self, timeout: float = 1.0) -> bool:
        return self._called.wait(timeout)


def test_broadcast_uses_registered_loop_from_thread() -> None:
    fake = _FakeWebSocket()
    original_clients = set(impl_server._clients)  # type: ignore[attr-defined]
    impl_server._clients.clear()  # type: ignore[attr-defined]
    impl_server._clients.add(fake)  # type: ignore[attr-defined]

    loop = asyncio.new_event_loop()
    impl_server._register_broadcast_loop(loop, force=True)  # type: ignore[attr-defined]

    def _runner() -> None:
        asyncio.set_event_loop(loop)
        loop.run_forever()

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    try:
        public_server.broadcast({"ping": "pong"})
        assert fake.wait(1.0)
        assert fake.messages == ['{"ping":"pong"}']
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=1.0)
        loop.close()
        impl_server._register_broadcast_loop(None, force=True)  # type: ignore[attr-defined]
        impl_server._clients.clear()  # type: ignore[attr-defined]
        impl_server._clients.update(original_clients)  # type: ignore[attr-defined]
