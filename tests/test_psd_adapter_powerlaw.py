import asyncio

import portfolio_exporter.psd_adapter as psd_adapter


def test_snapshot_once_includes_powerlaw(monkeypatch):
    async def _positions():
        return []

    async def _marks(_positions):
        return {}

    async def _greeks(_positions, _marks):
        return {"delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0}

    async def _risk(_positions, _marks, _greeks):
        return {"beta": 0.0, "var95_1d": 0.0, "margin_pct": 0.0, "notional": 0.0}

    monkeypatch.setattr(psd_adapter, "load_positions", _positions)
    monkeypatch.setattr(psd_adapter, "get_marks", _marks)
    monkeypatch.setattr(psd_adapter, "compute_greeks", _greeks)
    monkeypatch.setattr(psd_adapter, "compute_risk", _risk)
    monkeypatch.setattr(
        psd_adapter,
        "load_powerlaw_snapshot",
        lambda: {"as_of": "2025-01-03", "stale": False},
    )

    snapshot = asyncio.run(psd_adapter.snapshot_once())
    assert snapshot["powerlaw"]["as_of"] == "2025-01-03"
