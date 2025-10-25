from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from prometheus_client import REGISTRY

from psd.core import store
from psd.web.app import broadcast_latest_stats, create_app
from psd.web.config import Settings

try:
    from starlette.testclient import TestClient
except (RuntimeError, ModuleNotFoundError) as exc:  # pragma: no cover - optional dep missing
    pytest.skip(str(exc), allow_module_level=True)


@pytest.fixture(name="tmp_db")
def fixture_tmp_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    db_path = tmp_path / "stats.db"
    monkeypatch.setenv("PSD_DB", str(db_path))
    store.init()
    return db_path


def _write_snapshot(updated_at: datetime) -> None:
    snapshot = {
        "ts": updated_at.timestamp(),
        "positions": [],
        "quotes": {},
        "stats": {
            "day_pnl": 1250.5,
            "unrealized_pnl": 3400.75,
            "sigma_total": 18.2,
            "sigma_per_day": -0.65,
            "net_liq": 1_200_000.0,
            "var_95": 45_000.0,
            "margin_pct": 0.42,
            "updated_at": updated_at.isoformat(),
            "session": {
                "exchange": "XNYS",
                "tz": "America/New_York",
                "state": "ETH",
                "as_of": updated_at.isoformat(),
            },
            "session_info": {
                "exchange": "XNYS",
                "tz": "America/New_York",
                "state": "ETH",
                "as_of": updated_at.isoformat(),
            },
            "data_source": "fixture",
        },
    }
    store.write_snapshot(snapshot)


def _explicit_positions_view() -> dict[str, object]:
    combo_leg_long = {
        "secType": "OPT",
        "symbol": "AAPL",
        "conId": 501,
        "qty": 1,
        "avg_cost": 4.0,
        "multiplier": 100,
        "mark": 5.5,
        "price_source": "engine",
        "stale_s": 12.0,
        "pnl_intraday": 80.0,
        "right": "CALL",
        "strike": 110.0,
        "expiry": "20250117",
    }
    combo_leg_short = {
        "secType": "OPT",
        "symbol": "AAPL",
        "conId": 502,
        "qty": -1,
        "avg_cost": 2.0,
        "multiplier": 100,
        "mark": 1.0,
        "price_source": "engine",
        "stale_s": 12.0,
        "pnl_intraday": 40.0,
        "right": "CALL",
        "strike": 120.0,
        "expiry": "20250117",
    }
    return {
        "single_stocks": [
            {
                "secType": "STK",
                "symbol": "AAPL",
                "conId": 400,
                "qty": 10,
                "avg_cost": 100.0,
                "mark": 111.0,
                "price_source": "engine",
                "stale_s": 30.0,
                "pnl_intraday": 120.0,
            }
        ],
        "option_combos": [
            {
                "combo_id": "spread-1",
                "name": "Call Spread",
                "underlier": "AAPL",
                "pnl_intraday": 120.0,
                "legs": [combo_leg_long, combo_leg_short],
                "greeks_agg": {"delta": 0.4, "theta": -0.2},
            }
        ],
        "single_options": [
            {
                "secType": "OPT",
                "symbol": "AAPL",
                "conId": 601,
                "qty": -1,
                "avg_cost": 2.0,
                "multiplier": 100,
                "mark": 1.5,
                "price_source": "manual",
                "stale_s": 15.0,
                "pnl_intraday": -50.0,
                "right": "CALL",
                "strike": 125.0,
                "expiry": "20250117",
            }
        ],
    }


def test_stats_current_serves_last_good_snapshot(tmp_db):
    three_hours_ago = datetime.now(tz=timezone.utc) - timedelta(hours=3)
    _write_snapshot(three_hours_ago)

    app = create_app(Settings(test_mode=True, disable_background=True))
    with TestClient(app) as client:
        response = client.get("/stats/current")
    assert response.status_code == 200
    payload = response.json()

    assert payload["day_pnl"] == pytest.approx(1250.5)
    assert payload["unrealized_pnl"] == pytest.approx(3400.75)
    assert payload["sigma_total"] == pytest.approx(18.2)
    assert payload["sigma_per_day"] == pytest.approx(-0.65)
    assert payload["net_liq"] == pytest.approx(1_200_000.0)
    assert payload["var_95"] == pytest.approx(45_000.0)
    assert payload["margin_pct"] == pytest.approx(0.42)
    assert payload["session"]["state"] == "ETH"
    assert payload["session_info"]["state"] == "ETH"
    assert payload["data_source"] == "fixture"

    updated_at = datetime.fromisoformat(payload["updated_at"])
    assert updated_at.tzinfo is not None
    staleness = float(payload["staleness_sec"])
    assert staleness >= 10_000

    with TestClient(app) as client:
        stale_guard = client.get("/stats/current", params={"fresh_within_sec": "600"})
    assert stale_guard.status_code == 204


def test_broadcast_latest_stats_emits_event(tmp_db, monkeypatch: pytest.MonkeyPatch):
    timestamp = datetime.now(tz=timezone.utc) - timedelta(hours=2)
    _write_snapshot(timestamp)

    app = create_app(Settings(test_mode=True, disable_background=True))
    events: list[tuple[str, dict[str, object]]] = []

    def _capture(event_type: str, payload: dict[str, object]) -> None:
        events.append((event_type, payload))

    monkeypatch.setattr(app.state.sse, "broadcast", _capture)
    before = REGISTRY.get_sample_value(
        "psd_stats_broadcasts_total",
        {"trigger": "manual"},
    ) or 0.0
    broadcasted = broadcast_latest_stats(app)

    assert broadcasted is True
    assert events, "Expected one stats SSE broadcast"
    event_name, payload = events[-1]
    assert event_name == "psd.stats.update"
    assert payload["staleness_sec"] >= 0
    assert payload["day_pnl"] == pytest.approx(1250.5)
    after = REGISTRY.get_sample_value(
        "psd_stats_broadcasts_total",
        {"trigger": "manual"},
    ) or 0.0
    assert after == pytest.approx(before + 1.0)


def test_read_last_stats_aggregates_explicit_marks(tmp_db):
    timestamp = datetime.now(tz=timezone.utc)
    snapshot = {
        "ts": timestamp.timestamp(),
        "positions_view": _explicit_positions_view(),
        "stats": {"updated_at": timestamp.isoformat()},
    }
    store.write_snapshot(snapshot)

    stats = store.read_last_stats()

    assert stats is not None
    assert stats["day_pnl"] == pytest.approx(190.0)
    assert stats["unrealized_pnl"] == pytest.approx(410.0)


def test_stats_current_with_explicit_marks(tmp_db):
    timestamp = datetime.now(tz=timezone.utc)
    snapshot = {
        "ts": timestamp.timestamp(),
        "positions_view": _explicit_positions_view(),
        "stats": {"updated_at": timestamp.isoformat()},
    }
    store.write_snapshot(snapshot)

    app = create_app(Settings(test_mode=True, disable_background=True))
    with TestClient(app) as client:
        response = client.get("/stats/current")

    assert response.status_code == 200
    payload = response.json()

    assert payload["day_pnl"] == pytest.approx(190.0)
    assert payload["unrealized_pnl"] == pytest.approx(410.0)
    assert float(payload["staleness_sec"]) >= 0.0
