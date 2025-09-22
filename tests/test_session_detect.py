from __future__ import annotations

from datetime import datetime
from importlib import import_module
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from zoneinfo import ZoneInfo

from positions_engine.core.session import SessionInfo, detect_session

NY_TZ = ZoneInfo("America/New_York")


@pytest.fixture()
def api_main(monkeypatch):
    import sys

    service_module = import_module("positions_engine.service")

    class _StubRulesCatalogState:
        def __init__(self, *_, **__):
            pass

    monkeypatch.setattr(service_module, "RulesCatalogState", _StubRulesCatalogState)

    if "apps.api.main" in sys.modules:
        del sys.modules["apps.api.main"]

    module = import_module("apps.api.main")

    class _FakeRulesState:
        def __init__(self) -> None:
            self.rules = []

        def evaluate(self) -> SimpleNamespace:
            return SimpleNamespace(breaches=[], duration_ms=0.123)

    monkeypatch.setattr(module, "_rules_state", _FakeRulesState())
    monkeypatch.setattr(
        module._state,
        "stats",
        lambda: {
            "equity_count": 1,
            "option_legs_count": 0,
            "combos_matched": 0,
            "stale_quotes_count": 0,
        },
    )
    monkeypatch.setattr(module._state, "snapshot_updated_at", lambda: None)
    monkeypatch.setattr(
        module._state,
        "snapshot_payload",
        lambda: {
            "equities": [],
            "options": [],
        },
    )

    return module


@pytest.fixture()
def client(api_main) -> TestClient:
    return TestClient(api_main.app)


@pytest.mark.parametrize(
    ("now", "expected_state"),
    [
        (datetime(2024, 5, 6, 10, 0, tzinfo=NY_TZ), "RTH"),
        (datetime(2024, 5, 6, 6, 30, tzinfo=NY_TZ), "ETH"),
        (datetime(2024, 5, 6, 18, 15, tzinfo=NY_TZ), "ETH"),
        (datetime(2024, 5, 5, 12, 0, tzinfo=NY_TZ), "CLOSED"),
    ],
)
def test_detect_session_fallback(
    monkeypatch, now: datetime, expected_state: str
) -> None:
    monkeypatch.delenv("FORCE_SESSION_STATE", raising=False)
    info = detect_session(now=now)

    assert isinstance(info, SessionInfo)
    assert info.state == expected_state
    assert info.source in {"calendar", "fallback"}


def test_detect_session_override(monkeypatch) -> None:
    monkeypatch.setenv("FORCE_SESSION_STATE", "rth")
    info = detect_session(now=datetime(2024, 5, 5, 12, tzinfo=NY_TZ))

    assert info.state == "RTH"
    assert info.source == "override"
    assert info.note is None


def test_detect_session_invalid_override(monkeypatch) -> None:
    monkeypatch.setenv("FORCE_SESSION_STATE", "lunch")
    info = detect_session(now=datetime(2024, 5, 5, 12, tzinfo=NY_TZ))

    assert info.state == "CLOSED"
    assert info.source == "override"
    assert info.note and "invalid" in info.note


def test_detect_session_with_calendar(monkeypatch) -> None:
    pytest.importorskip("exchange_calendars")
    monkeypatch.delenv("FORCE_SESSION_STATE", raising=False)
    now = datetime(2024, 5, 6, 10, 0, tzinfo=NY_TZ)
    info = detect_session(now=now)

    assert info.state == "RTH"
    assert info.source == "calendar"
    assert info.rth_open is not None
    assert info.rth_close is not None


def test_session_endpoint(client: TestClient, monkeypatch) -> None:
    monkeypatch.delenv("FORCE_SESSION_STATE", raising=False)
    response = client.get("/session")

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] in {"RTH", "ETH", "CLOSED"}
    assert payload["tz"] == "America/New_York"


def test_stats_includes_session(client: TestClient, monkeypatch) -> None:
    monkeypatch.delenv("FORCE_SESSION_STATE", raising=False)
    response = client.get("/stats")
    assert response.status_code == 200

    payload = response.json()
    assert "session" in payload
    assert payload["session"]["state"] in {"RTH", "ETH", "CLOSED"}


def test_state_includes_session(client: TestClient, monkeypatch) -> None:
    monkeypatch.delenv("FORCE_SESSION_STATE", raising=False)
    response = client.get("/state")
    assert response.status_code == 200

    payload = response.json()
    assert payload.get("session") in {"RTH", "ETH", "CLOSED", "EXT"}
    assert "session_info" in payload
    assert payload["session_info"]["state"] in {"RTH", "ETH", "CLOSED"}


def test_debug_override_endpoint(client: TestClient) -> None:
    response = client.get("/debug/session/override/rth")
    assert response.status_code == 200
    payload = response.json()
    assert payload["state"] == "RTH"
    assert payload["source"] == "override"

    clear = client.get("/debug/session/clear")
    assert clear.status_code == 200
    assert clear.json()["source"] in {"fallback", "calendar"}
