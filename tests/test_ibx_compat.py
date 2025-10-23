from __future__ import annotations

import asyncio

from portfolio_exporter.ibx import compat as ibx


class DummyIB:
    def __init__(self) -> None:
        self.connected = False
        self.calls = 0

    async def connectAsync(self, *args, **kwargs):
        await asyncio.sleep(0)
        self.connected = True

    def connect(self, *args, **kwargs):
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def isConnected(self) -> bool:
        return self.connected

    async def reqPositionsAsync(self):
        self.calls += 1
        await asyncio.sleep(0)
        return [("AAPL", 1)]

    def reqPositions(self):
        self.calls += 1
        return [("AAPL", 1)]


def test_connect_single_flight() -> None:
    real_ib = ibx.IB
    ibx.IB = DummyIB  # type: ignore

    async def runner() -> None:
        await ibx.disconnect()
        first, second = await asyncio.gather(
            ibx.connect("h", 1, 1),
            ibx.connect("h", 1, 1),
        )
        assert first is second
        assert first.isConnected()
        await ibx.disconnect()

    try:
        asyncio.run(runner())
    finally:
        ibx.IB = real_ib
        asyncio.run(ibx.disconnect())


def test_req_positions_prefers_async() -> None:
    real_ib = ibx.IB
    ibx.IB = DummyIB  # type: ignore

    async def runner() -> None:
        await ibx.disconnect()
        ib = await ibx.connect("h", 1, 1)
        res = await ibx.req_positions(ib)
        assert res
        assert ib.calls == 1
        await ibx.disconnect()

    try:
        asyncio.run(runner())
    finally:
        ibx.IB = real_ib
        asyncio.run(ibx.disconnect())
