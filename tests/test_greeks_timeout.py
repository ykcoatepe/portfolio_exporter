from __future__ import annotations

import asyncio

import pandas as pd
import pytest

from src.psd.datasources import ibkr


@pytest.fixture(autouse=True)
def _attach_event_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        yield
    finally:
        loop.close()
        asyncio.set_event_loop(None)


def _option_snapshot() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["AAPL"],
            "underlying": ["AAPL"],
            "secType": ["OPT"],
            "qty": [1],
            "price": [2.5],
            "right": ["C"],
            "strike": [180.0],
            "expiry": ["20240119"],
            "delta": [None],
            "delta_exposure": [None],
            "multiplier": [100],
            "underlying_price": [190.0],
        }
    )


def test_missing_greeks_logs_warning(monkeypatch, caplog) -> None:
    from portfolio_exporter.scripts import portfolio_greeks as pg  # type: ignore

    async def fake_loader():
        return _option_snapshot()

    monkeypatch.setattr(pg, "_load_positions", fake_loader)
    monkeypatch.setattr(pg, "load_positions_sync", lambda: _option_snapshot())
    caplog.set_level("WARNING")

    positions = ibkr.get_positions({})
    option = next(p for p in positions if p["kind"] == "option")
    assert option["legs"][0].delta is None
    assert any("Greeks unavailable" in record.getMessage() for record in caplog.records)
