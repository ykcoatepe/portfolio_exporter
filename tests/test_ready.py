from __future__ import annotations

from pathlib import Path
import sys

from starlette.testclient import TestClient

SRC_ROOT = Path(__file__).resolve().parents[1]
SRC_SRC = SRC_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(SRC_SRC) not in sys.path:
    sys.path.insert(0, str(SRC_SRC))

import psd.web.app as web_app
import psd.web.ready as ready


def test_ready_requires_snapshot(monkeypatch):
    monkeypatch.setattr(ready, "latest_snapshot", lambda: None)

    with TestClient(web_app.app) as client:
        resp = client.get("/ready")

    assert resp.status_code == 503
    payload = resp.json()
    assert payload["ok"] is False
    assert payload["data_age_s"] is None
    assert "snapshot" in payload["reason"].lower()


def test_ready_rejects_stale_data(monkeypatch):
    monkeypatch.setattr(ready, "latest_snapshot", lambda: {"ts": 123})
    monkeypatch.setattr(
        ready,
        "latest_health",
        lambda: {"data_age_s": 90.0, "ibkr_connected": True},
    )
    monkeypatch.delenv("PSD_READY_MAX_AGE", raising=False)

    with TestClient(web_app.app) as client:
        resp = client.get("/ready")

    assert resp.status_code == 503
    payload = resp.json()
    assert payload["ok"] is False
    assert payload["data_age_s"] == 90.0
    assert "stale data" in payload["reason"].lower()


def test_ready_accepts_recent_data(monkeypatch):
    monkeypatch.setattr(ready, "latest_snapshot", lambda: {"ts": 456})
    monkeypatch.setattr(
        ready,
        "latest_health",
        lambda: {"data_age_s": 10.0, "ibkr_connected": False, "ts": 111.0},
    )
    monkeypatch.setenv("PSD_READY_MAX_AGE", "20")

    with TestClient(web_app.app) as client:
        resp = client.get("/ready")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["data_age_s"] == 10.0
    assert payload["threshold_s"] == 20.0
    assert payload["ibkr_connected"] is False
    assert payload["health_ts"] == 111.0


def test_ready_handles_invalid_age(monkeypatch):
    monkeypatch.setattr(ready, "latest_snapshot", lambda: {"ts": 789})
    monkeypatch.setattr(ready, "latest_health", lambda: {"data_age_s": "nan"})
    monkeypatch.delenv("PSD_READY_MAX_AGE", raising=False)

    with TestClient(web_app.app) as client:
        resp = client.get("/ready")

    assert resp.status_code == 503
    payload = resp.json()
    assert payload["ok"] is False
    assert payload["data_age_s"] is None
    assert "missing" in payload["reason"].lower()
