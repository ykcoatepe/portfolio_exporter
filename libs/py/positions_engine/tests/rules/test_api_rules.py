# SPDX-License-Identifier: MIT

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys

import pytest
from starlette.testclient import TestClient

ROOT = Path(__file__).resolve().parents[5]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from apps.api import main as api_main
from positions_engine.rules import Rule
from positions_engine.service.rules_state import RulesState


@pytest.fixture
def client() -> TestClient:
    with TestClient(api_main.app) as test_client:
        yield test_client


def _fixed_now() -> datetime:
    return datetime(2025, 9, 19, 9, 0, tzinfo=UTC)


def test_rules_summary_returns_counters_and_top(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    now = _fixed_now()
    rules = [
        Rule(
            rule_id="combo_high",
            name="High premium combo",
            severity="CRITICAL",
            scope="COMBO",
            filter="dte <= 7",
            expr="annualized_premium_pct >= 30",
        ),
        Rule(
            rule_id="leg_iv_missing",
            name="IV missing",
            severity="WARNING",
            scope="LEG",
            filter="dte <= 5",
            expr="iv is None",
        ),
        Rule(
            rule_id="leg_stale",
            name="Stale mark",
            severity="CRITICAL",
            scope="LEG",
            filter="",
            expr="stale_seconds > 900",
        ),
        Rule(
            rule_id="ul_delta",
            name="Underlying delta",
            severity="WARNING",
            scope="UL",
            filter="",
            expr="delta > 1.2 or delta < -1.2",
        ),
        Rule(
            rule_id="port_theta",
            name="Net theta",
            severity="INFO",
            scope="PORT",
            filter="",
            expr="net_theta_per_day < 0",
        ),
    ]

    original_rules = api_main._rules_state.rules
    api_main._rules_state.set_rules(rules)

    def fake_build_rows(self: RulesState, _timestamp: datetime) -> dict[str, list[dict[str, object]]]:
        return {
            "COMBO": [
                {
                    "subject_id": "combo-1",
                    "symbol": "TSLA",
                    "dte": 6,
                    "annualized_premium_pct": 42.1,
                    "value": 42.1,
                    "triggered_at": now,
                }
            ],
            "LEG": [
                {
                    "subject_id": "leg-1",
                    "symbol": "TSLA230920C",
                    "dte": 3,
                    "iv": None,
                    "stale_seconds": 1_200,
                    "value": 1_200,
                    "triggered_at": now,
                }
            ],
            "UL": [
                {
                    "subject_id": "TSLA",
                    "symbol": "TSLA",
                    "delta": 1.3,
                    "value": 1.3,
                    "triggered_at": now,
                }
            ],
            "PORT": [
                {
                    "subject_id": "PORT",
                    "net_theta_per_day": -12.5,
                    "value": -12.5,
                    "triggered_at": now,
                }
            ],
        }

    monkeypatch.setattr(RulesState, "_build_rows", fake_build_rows)

    try:
        response = client.get("/rules/summary")
        assert response.status_code == 200
        payload = response.json()

        assert payload["rules_total"] == 5
        assert payload["counters"] == {"total": 5, "critical": 2, "warning": 2, "info": 1}
        assert 0 < len(payload["top"]) <= 5
        top_rules = {item["rule"] for item in payload["top"]}
        assert top_rules == {"High premium combo", "IV missing", "Stale mark", "Underlying delta", "Net theta"}
        severities = {item["severity"] for item in payload["top"]}
        assert severities == {"critical", "warning", "info"}
        assert set(payload["focus_symbols"]) == {"TSLA", "TSLA230920C"}
        assert payload["as_of"].endswith("Z")
        assert payload["evaluation_ms"] >= 0

        stats_resp = client.get("/stats")
        assert stats_resp.status_code == 200
        stats = stats_resp.json()
        assert stats["rules_count"] == 5
        assert stats["breaches_count"] == 5
        assert "rules_eval_ms" in stats and stats["rules_eval_ms"] >= 0
        assert "trades_prior_positions" in stats
    finally:
        api_main._rules_state.set_rules(original_rules)
