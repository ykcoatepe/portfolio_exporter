from __future__ import annotations

import asyncio

import pandas as pd
import pytest

from src.psd.datasources import ibkr, yfin
from src.psd.ui import cli


@pytest.fixture(autouse=True)
def _attach_event_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        yield
    finally:
        loop.close()
        asyncio.set_event_loop(None)


def _snapshot(mark: float | None) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["AAPL"],
            "underlying": ["AAPL"],
            "secType": ["STK"],
            "qty": [10],
            "price": [mark],
        }
    )


def test_equity_mark_backfills_from_yfinance(monkeypatch) -> None:
    from portfolio_exporter.scripts import portfolio_greeks as pg  # type: ignore

    monkeypatch.setattr(pg, "_load_positions", lambda: _snapshot(None))
    monkeypatch.setattr(yfin, "fill_equity_marks_from_yf", lambda symbols: {"AAPL": 197.25})
    ibkr.consume_mark_backfills()

    positions = ibkr.get_positions({"fill": {"allow_yf_equity_marks": True}})
    equity = next(p for p in positions if p["kind"] == "equity")
    assert equity["mark"] == pytest.approx(197.25)
    assert ibkr.consume_mark_backfills() == ["AAPL"]


def test_none_mark_renders_dash_placeholder(monkeypatch) -> None:
    from portfolio_exporter.scripts import portfolio_greeks as pg  # type: ignore

    monkeypatch.setattr(pg, "_load_positions", lambda: _snapshot(None))
    monkeypatch.setattr(yfin, "fill_equity_marks_from_yf", lambda symbols: {"AAPL": None})
    ibkr.consume_mark_backfills()

    positions = ibkr.get_positions({"fill": {"allow_yf_equity_marks": True}})
    equity = next(p for p in positions if p["kind"] == "equity")
    assert equity["mark"] is None

    table = cli.render_table(
        [
            {
                "uid": "STK-AAPL",
                "sleeve": "core",
                "kind": "equity",
                "R": "-",
                "stop": "-",
                "target": "-",
                "mark": equity["mark"],
                "alert": "",
            }
        ]
    )
    assert "—" in table.splitlines()[-1]
