from __future__ import annotations

from datetime import datetime, timezone
from importlib import import_module
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


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
            self.rules = [object(), object()]

        def evaluate(self) -> SimpleNamespace:
            return SimpleNamespace(breaches=[object()], duration_ms=1.234)

    monkeypatch.setattr(module, "_rules_state", _FakeRulesState())
    monkeypatch.setattr(module._state, "snapshot_updated_at", lambda: None)

    return module


@pytest.fixture()
def client(api_main) -> TestClient:
    return TestClient(api_main.app)


def test_updated_at_prefers_stats_payload(client: TestClient, api_main, monkeypatch) -> None:
    stats_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    snapshot_ts = datetime(2023, 12, 31, tzinfo=timezone.utc)

    def stats_with_timestamp() -> dict[str, object]:
        return {
            "equity_count": 1,
            "option_legs_count": 0,
            "combos_matched": 0,
            "stale_quotes_count": 0,
            "updated_at": stats_ts,
        }

    monkeypatch.setattr(api_main._state, "stats", stats_with_timestamp)
    monkeypatch.setattr(api_main._state, "snapshot_updated_at", lambda: snapshot_ts)

    response = client.get("/stats")
    payload = response.json()

    assert response.status_code == 200
    assert payload["updated_at"].startswith("2024-01-01")


def test_updated_at_uses_snapshot_when_missing(client: TestClient, api_main, monkeypatch) -> None:
    snapshot_ts = datetime(2024, 2, 1, 12, tzinfo=timezone.utc)

    def stats_without_timestamp() -> dict[str, object]:
        return {
            "equity_count": 1,
            "option_legs_count": 0,
            "combos_matched": 0,
            "stale_quotes_count": 0,
        }

    monkeypatch.setattr(api_main._state, "stats", stats_without_timestamp)
    monkeypatch.setattr(api_main._state, "snapshot_updated_at", lambda: snapshot_ts)

    response = client.get("/stats")
    payload = response.json()

    assert response.status_code == 200
    assert payload["updated_at"].startswith("2024-02-01T12:00:00")


def test_updated_at_omitted_when_unknown(client: TestClient, api_main, monkeypatch) -> None:
    def stats_without_timestamp() -> dict[str, object]:
        return {
            "equity_count": 1,
            "option_legs_count": 0,
            "combos_matched": 0,
            "stale_quotes_count": 0,
        }

    monkeypatch.setattr(api_main._state, "stats", stats_without_timestamp)
    monkeypatch.setattr(api_main._state, "snapshot_updated_at", lambda: None)

    response = client.get("/stats")
    payload = response.json()

    assert response.status_code == 200
    assert "updated_at" not in payload
