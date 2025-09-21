from __future__ import annotations

import asyncio

from portfolio_exporter import psd_adapter


def test_snapshot_once_roundtrip(monkeypatch):
    fake_positions = [{"symbol": "AAPL", "qty": 10, "multiplier": 1}]
    fake_marks = {"AAPL": {"price": 190.5, "source": "delayed"}}
    fake_greeks = {"delta": 42.0, "gamma": 0.1, "vega": 0.2, "theta": -0.3}
    fake_risk = {"beta": 0.12, "var95_1d": 0.02, "margin_pct": 0.1, "notional": 1000.0}

    async def _positions():
        return fake_positions

    async def _marks(positions):
        assert positions is fake_positions
        return fake_marks

    async def _greeks(positions, marks):
        assert positions is fake_positions
        assert marks is fake_marks
        return fake_greeks

    async def _risk(positions, marks, greeks):
        assert greeks is fake_greeks
        return fake_risk

    fake_positions_view = {"single_stocks": [], "option_combos": [], "single_options": []}

    monkeypatch.setattr(psd_adapter, "load_positions", _positions)
    monkeypatch.setattr(psd_adapter, "get_marks", _marks)
    monkeypatch.setattr(psd_adapter, "compute_greeks", _greeks)
    monkeypatch.setattr(psd_adapter, "compute_risk", _risk)
    monkeypatch.setattr(psd_adapter, "split_positions", lambda _pos, _session: fake_positions_view)
    monkeypatch.setattr(psd_adapter, "_resolve_session", lambda: "EXT")

    snap = asyncio.run(psd_adapter.snapshot_once())
    assert set(snap.keys()) == {"ts", "session", "positions", "positions_view", "quotes", "risk"}
    assert isinstance(snap["ts"], float)
    assert snap["session"] == "EXT"
    assert snap["positions"] is fake_positions
    assert snap["positions_view"] is fake_positions_view
    assert snap["quotes"] is fake_marks
    assert snap["risk"] is fake_risk


def test_snapshot_with_delayed_marks(monkeypatch):
    async def _positions():
        return [{"symbol": "MSFT", "qty": 5, "multiplier": 1}]

    async def _marks(_positions):
        return {"MSFT": {"price": 330.0, "source": "delayed"}}

    async def _greeks(_positions, marks):
        # verify nested dict is passed through
        assert marks["MSFT"]["source"] == "delayed"
        return {"delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0}

    async def _risk(_positions, marks, greeks):
        # ensure still invoked even when marks carry metadata
        return {"beta": 0.0, "var95_1d": 0.0, "margin_pct": 0.0, "notional": 0.0}

    monkeypatch.setattr(psd_adapter, "load_positions", _positions)
    monkeypatch.setattr(psd_adapter, "get_marks", _marks)
    monkeypatch.setattr(psd_adapter, "compute_greeks", _greeks)
    monkeypatch.setattr(psd_adapter, "compute_risk", _risk)
    monkeypatch.setattr(psd_adapter, "split_positions", lambda _pos, _session: {"single_stocks": [], "option_combos": [], "single_options": []})
    monkeypatch.setattr(psd_adapter, "_resolve_session", lambda: "EXT")

    snap = asyncio.run(psd_adapter.snapshot_once())
    assert snap["quotes"]["MSFT"]["source"] == "delayed"
    assert snap["risk"]["notional"] == 0.0
    assert snap["session"] == "EXT"
    assert snap["positions_view"] == {"single_stocks": [], "option_combos": [], "single_options": []}
