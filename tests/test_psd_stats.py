from __future__ import annotations

import pytest

from psd.analytics.stats import compute_stats
from psd.core import store

try:
    from starlette.testclient import TestClient
except (RuntimeError, ModuleNotFoundError) as exc:  # pragma: no cover - optional dep
    pytest.skip(str(exc), allow_module_level=True)

from psd.web.app import app


@pytest.fixture(name="sample_snapshot")
def fixture_sample_snapshot() -> dict[str, object]:
    return {
        "ts": 1_700_000_000.0,
        "positions": [
            {
                "uid": "combo1",
                "symbol": "SPY",
                "sleeve": "theta",
                "kind": "option",
                "qty": -1,
                "mark": 1.25,
                "legs": [
                    {"symbol": "SPY", "expiry": "20250117", "right": "C", "strike": 430.0, "qty": -1, "price": 2.50},
                    {"symbol": "SPY", "expiry": "20250117", "right": "C", "strike": 435.0, "qty": 1, "price": 1.05},
                    {"symbol": "SPY", "expiry": "20250117", "right": "P", "strike": 410.0, "qty": -1, "price": 2.30},
                    {"symbol": "SPY", "expiry": "20250117", "right": "P", "strike": 405.0, "qty": 1, "price": 1.10},
                ],
            },
            {
                "uid": "eq1",
                "symbol": "MSFT",
                "sleeve": "core",
                "kind": "equity",
                "qty": 50,
                "mark": 310.0,
            },
        ],
        "quotes": {
            "SPY": {"price": 433.0, "ts": 1_699_999_000.0},
            "MSFT": {"price": 310.0, "age_s": 1_200.0},
        },
    }


def test_compute_stats_detects_combos_and_staleness(sample_snapshot: dict[str, object]) -> None:
    stats = compute_stats(sample_snapshot)
    assert stats["positions_count"] == 2
    assert stats["option_legs_count"] == 4
    assert stats["combos_matched"] == 1
    assert stats["stale_quotes_count"] == 2
    assert stats["stale_threshold_seconds"] >= 0


def test_stats_endpoint_returns_payload(monkeypatch: pytest.MonkeyPatch, tmp_path, sample_snapshot: dict[str, object]) -> None:
    db_path = tmp_path / "stats.db"
    monkeypatch.setenv("PSD_DB", str(db_path))
    store.init()
    store.write_snapshot(sample_snapshot)

    with TestClient(app) as client:
        response = client.get("/stats")
    assert response.status_code == 200
    payload = response.json()
    assert payload["empty"] is False
    assert payload["positions_count"] == 2
    assert payload["option_legs_count"] == 4
    assert payload["combos_matched"] == 1
    assert payload["quotes_count"] == 2
    assert payload["stale_quotes_count"] == 2


def test_stats_endpoint_empty_snapshot(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    db_path = tmp_path / "stats-empty.db"
    monkeypatch.setenv("PSD_DB", str(db_path))
    store.init()

    with TestClient(app) as client:
        response = client.get("/stats")
    assert response.status_code == 200
    payload = response.json()
    assert payload["empty"] is True
    assert payload["positions_count"] == 0
    assert payload["stale_quotes_count"] == 0
    assert payload["quotes_count"] == 0
