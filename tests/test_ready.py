from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

SRC_ROOT = Path(__file__).resolve().parents[1]
SRC_SRC = SRC_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(SRC_SRC) not in sys.path:
    sys.path.insert(0, str(SRC_SRC))

import psd.web.app as web_app
import psd.web.ready as ready
from psd.web.config import Settings

pytestmark = pytest.mark.integration


@pytest.fixture()
def api_app() -> FastAPI:
    return web_app.create_app(Settings(test_mode=True, disable_background=True))


def test_ready_requires_snapshot(monkeypatch, api_app):
    monkeypatch.setattr(ready, "latest_snapshot", lambda: None)

    with TestClient(api_app) as client:
        resp = client.get("/ready")

    assert resp.status_code == 503
    payload = resp.json()
    assert payload["ok"] is False
    assert payload["data_age_s"] is None
    assert "snapshot" in payload["reason"].lower()


def test_ready_rejects_stale_data(monkeypatch, api_app):
    monkeypatch.setattr(ready, "latest_snapshot", lambda: {"ts": 123})
    monkeypatch.setattr(
        ready,
        "latest_health",
        lambda: {"data_age_s": 90.0, "ibkr_connected": True},
    )
    monkeypatch.delenv("PSD_READY_MAX_AGE", raising=False)

    with TestClient(api_app) as client:
        resp = client.get("/ready")

    assert resp.status_code == 503
    payload = resp.json()
    assert payload["ok"] is False
    assert payload["data_age_s"] == 90.0
    assert "stale data" in payload["reason"].lower()


def test_ready_accepts_recent_data(monkeypatch, api_app):
    monkeypatch.setattr(ready, "latest_snapshot", lambda: {"ts": 456})
    monkeypatch.setattr(
        ready,
        "latest_health",
        lambda: {"data_age_s": 10.0, "ibkr_connected": False, "ts": 111.0},
    )
    monkeypatch.setenv("PSD_READY_MAX_AGE", "20")

    with TestClient(api_app) as client:
        resp = client.get("/ready")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["data_age_s"] == 10.0
    assert payload["threshold_s"] == 20.0
    assert payload["ibkr_connected"] is False
    assert payload["health_ts"] == 111.0


def test_ready_handles_invalid_age(monkeypatch, api_app):
    monkeypatch.setattr(ready, "latest_snapshot", lambda: {"ts": 789})
    monkeypatch.setattr(ready, "latest_health", lambda: {"data_age_s": "nan"})
    monkeypatch.delenv("PSD_READY_MAX_AGE", raising=False)

    with TestClient(api_app) as client:
        resp = client.get("/ready")

    assert resp.status_code == 503
    payload = resp.json()
    assert payload["ok"] is False
    assert payload["data_age_s"] is None
    assert "missing" in payload["reason"].lower()
