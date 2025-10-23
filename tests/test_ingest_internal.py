from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from positions_engine.ingest.csv import CsvLoadResult

import apps.api.main as api


def test_internal_provider_precedence(monkeypatch):
    """Internal provider should populate PSD endpoints without CSV uploads."""

    if os.getenv("PE_TEST_MODE") == "1":
        pytest.skip("Internal provider precedence requires PE_TEST_MODE unset")

    positions_view = {
        "single_stocks": [
            {
                "symbol": "AAPL",
                "qty": 10,
                "avg_cost": 150.0,
                "mark": 155.0,
                "previous_close": 152.5,
            }
        ],
        "option_combos": [
            {
                "underlying": "TSLA",
                "legs": [
                    {
                        "symbol": "TSLA 20251018C00750000",
                        "right": "CALL",
                        "strike": 750,
                        "expiry": "2025-10-18",
                        "quantity": 1,
                        "mark": 12.5,
                        "greeks": {"delta": 0.42, "theta": -0.03},
                    }
                ],
            }
        ],
        "single_options": [
            {
                "symbol": "MSFT 20251018P00320000",
                "right": "PUT",
                "strike": 320,
                "expiry": "2025-10-18",
                "quantity": -1,
                "mark": 5.1,
                "greeks": {"delta": -0.18, "theta": -0.02},
            }
        ],
    }

    async def _fake_snapshot_once() -> dict[str, object]:
        return {
            "positions_view": positions_view,
            "positions": [],
            "quotes": {},
        }

    def _empty_csv(_base_dir: object) -> CsvLoadResult:
        return CsvLoadResult(
            positions=[],
            quotes=[],
            metadata={
                "data_root": "test",
                "positions_rows": 0,
                "quotes_rows": 0,
                "greeks_rows": 0,
            },
        )

    monkeypatch.setenv("POSITIONS_ENGINE_ALLOW_EMPTY", "1")
    monkeypatch.setenv("POSITIONS_ENGINE_DEMO", "0")
    monkeypatch.setattr("positions_engine.ingest.csv.load_csv_records", _empty_csv)
    monkeypatch.setattr(
        "portfolio_exporter.psd_adapter.snapshot_once", _fake_snapshot_once
    )

    api._DEMO_OVERRIDE = None
    api._state.refresh(positions=[], quotes=[], data_source="unknown")

    with TestClient(api.app) as client:
        stats = client.get("/stats").json()
        assert stats["data_source"] == "internal"
        stocks = client.get("/positions/stocks").json()
        assert len(stocks) == 1
        stock_row = stocks[0]
        assert stock_row.get("mark_source") in {"MID", "LAST", "PREV", "MISSING"}
        assert "stale_seconds" in stock_row
        assert "day_pnl" in stock_row
        assert "day_pnl_pct" in stock_row
        assert "pnl_unrealized" in stock_row
        assert "pnl_unrealized_percent" in stock_row
        assert "total_pnl" in stock_row
        options_payload = client.get("/positions/options").json()
        assert options_payload["legs"]
        assert any(
            leg["symbol"] == "TSLA 20251018C00750000" for leg in options_payload["legs"]
        )

        state_snapshot = client.get("/state").json()
        assert state_snapshot["data_source"] == "internal"
        view = state_snapshot.get("positions_view", {})
        assert isinstance(view, dict)
        single_stocks = view.get("single_stocks") or []
        assert len(single_stocks) >= 1
        first_single = single_stocks[0]
        assert first_single.get("mark_source") in {"MID", "LAST", "PREV", "MISSING"}
        stale_value = first_single.get("stale_seconds")
        assert stale_value is None or stale_value >= 0
        assert "day_pnl" in first_single
        assert "day_pnl_pct" in first_single
        assert "pnl_unrealized" in first_single
        assert "pnl_unrealized_percent" in first_single
        combo_legs = [
            leg
            for combo in view.get("option_combos", []) or []
            if isinstance(combo, dict)
            for leg in combo.get("legs", []) or []
            if isinstance(leg, dict)
        ]
        assert any(leg.get("symbol") == "TSLA 20251018C00750000" for leg in combo_legs)
        assert any(
            leg.get("symbol") == "MSFT 20251018P00320000"
            for leg in view.get("single_options", []) or []
            if isinstance(leg, dict)
        )

    detection = api._state.options_detection()
    assert detection.orphans or detection.combos
    assert api._state.data_source == "internal"
