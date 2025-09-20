from __future__ import annotations

import importlib
from pathlib import Path

from fastapi.testclient import TestClient


def _reload_api_module() -> None:
    import apps.api.main as api

    importlib.reload(api)


def test_demo_dataset_populates_positions(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("POSITIONS_ENGINE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("POSITIONS_ENGINE_DEMO", "1")
    monkeypatch.delenv("POSITIONS_ENGINE_ALLOW_EMPTY", raising=False)

    _reload_api_module()
    import apps.api.main as api

    api._state.refresh(positions=[], quotes=[], data_source="live")  # type: ignore[attr-defined]
    api._DEMO_OVERRIDE = None  # type: ignore[attr-defined]
    api._refresh_from_disk()  # type: ignore[attr-defined]

    with TestClient(api.app) as client:  # type: ignore[attr-defined]
        stocks = client.get("/positions/stocks").json()
        assert stocks, "demo dataset should yield equities"

        options_payload = client.get("/positions/options").json()
        combo_count = len(options_payload.get("combos", []))
        leg_count = len(options_payload.get("legs", []))
        assert combo_count + leg_count > 0, "demo dataset should yield option exposure"

        stats = client.get("/stats").json()
        assert stats["data_source"] == "demo"
        assert stats["equity_count"] > 0


def test_csv_priority(tmp_path, monkeypatch) -> None:
    positions_path = Path(tmp_path) / "live_positions_20250101.csv"
    positions_path.write_text(
        "symbol,qty,avg_cost,type,right,strike,expiry,underlying\n"
        "AAPL,10,150.5,EQUITY,,,\n"
        "SPY 20250117C00440000,1,2.1,OPTION,CALL,440,2025-01-17,SPY\n"
    )

    quotes_path = Path(tmp_path) / "live_quotes_20250101.csv"
    quotes_path.write_text(
        "symbol,bid,ask,last,prev_close,ts\n"
        "AAPL,150.4,150.6,150.5,149.9,2025-01-01T15:59:00Z\n"
        "SPY,430.1,430.3,430.2,429.8,2025-01-01T15:59:00Z\n"
    )

    greeks_path = Path(tmp_path) / "portfolio_greeks_totals.csv"
    greeks_path.write_text("symbol,delta,gamma,theta,vega\nSPY 20250117C00440000,0.25,0.01,-0.02,0.15\n")

    monkeypatch.setenv("POSITIONS_ENGINE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("POSITIONS_ENGINE_DEMO", "0")
    monkeypatch.setenv("POSITIONS_ENGINE_ALLOW_EMPTY", "1")

    _reload_api_module()
    import apps.api.main as api

    api._state.refresh(positions=[], quotes=[], data_source="live")  # type: ignore[attr-defined]
    api._DEMO_OVERRIDE = None  # type: ignore[attr-defined]
    api._refresh_from_disk()  # type: ignore[attr-defined]

    with TestClient(api.app) as client:  # type: ignore[attr-defined]
        stats = client.get("/stats").json()
        assert stats["data_source"] == "csv"
        assert stats["equity_count"] == 1
        assert stats["option_legs_count"] >= 1

        stocks = client.get("/positions/stocks").json()
        assert any(row["symbol"] == "AAPL" for row in stocks)


def test_stats_live_when_empty(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("POSITIONS_ENGINE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("POSITIONS_ENGINE_DEMO", "0")
    monkeypatch.setenv("POSITIONS_ENGINE_ALLOW_EMPTY", "1")

    _reload_api_module()
    import apps.api.main as api

    api._state.refresh(positions=[], quotes=[], data_source="live")  # type: ignore[attr-defined]
    api._DEMO_OVERRIDE = False  # type: ignore[attr-defined]
    api._refresh_from_disk()  # type: ignore[attr-defined]

    with TestClient(api.app) as client:  # type: ignore[attr-defined]
        stats = client.get("/stats").json()
        assert stats["data_source"] == "live"
        assert stats["equity_count"] == 0
        assert stats["option_legs_count"] == 0
