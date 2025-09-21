# SPDX-License-Identifier: MIT

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from starlette.testclient import TestClient

ROOT = Path(__file__).resolve().parents[5]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from positions_engine.rules import Rule
from positions_engine.service.rules_state import RulesState

from apps.api import main as api_main


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
            rule_id="combo_tp_reached",
            name="Playbook TP reached",
            severity="INFO",
            scope="COMBO",
            filter="",
            expr="tp_hit",
        ),
        Rule(
            rule_id="combo_tp_done",
            name="Playbook TP complete",
            severity="INFO",
            scope="COMBO",
            filter="",
            expr="tp_done",
        ),
        Rule(
            rule_id="combo_stop_hit",
            name="Playbook stop hit",
            severity="CRITICAL",
            scope="COMBO",
            filter="",
            expr="sl_hit",
        ),
        Rule(
            rule_id="unit_exit",
            name="Exit as unit",
            severity="INFO",
            scope="COMBO",
            filter="",
            expr="exit_as_unit and tp_done",
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
                    "tp_hit": True,
                    "tp_done": True,
                    "sl_hit": False,
                    "next_action": "TAKE_PROFIT",
                    "progress_pct_of_goal": 1.1,
                    "progress_pct_of_max": 1.0,
                    "tp_band_low_pct": 0.4,
                    "tp_band_high_pct": 0.6,
                    "exit_as_unit": True,
                    "value": 42.1,
                    "triggered_at": now,
                },
                {
                    "subject_id": "combo-2",
                    "symbol": "MSFT",
                    "dte": 9,
                    "annualized_premium_pct": 12.0,
                    "tp_hit": False,
                    "tp_done": False,
                    "sl_hit": True,
                    "next_action": "CUT",
                    "progress_pct_of_goal": -0.5,
                    "progress_pct_of_max": -0.8,
                    "tp_band_low_pct": 0.5,
                    "tp_band_high_pct": 0.7,
                    "exit_as_unit": False,
                    "value": -120.0,
                    "triggered_at": now,
                },
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

        assert payload["rules_total"] == 9
        assert payload["breaches"] == {"critical": 3, "warning": 2, "info": 4}
        assert sum(payload["breaches"].values()) == 9
        assert 0 < len(payload["top"]) <= 9
        top_rules = {item["rule"] for item in payload["top"]}
        expected_rules = {
            "High premium combo",
            "Playbook stop hit",
            "Stale mark",
            "IV missing",
            "Underlying delta",
        }
        assert expected_rules.issubset(top_rules)
        severities = {item["severity"] for item in payload["top"]}
        assert {"critical", "warning"}.issubset(severities)
        assert set(payload["focus_symbols"]) == {"TSLA", "MSFT", "TSLA230920C"}
        assert payload["as_of"].endswith("Z")
        assert payload["evaluation_ms"] >= 0

        stats_resp = client.get("/stats")
        assert stats_resp.status_code == 200
        stats = stats_resp.json()
        assert stats["rules_count"] == 9
        assert stats["breaches_count"] == 9
        assert "rules_eval_ms" in stats and stats["rules_eval_ms"] >= 0
        assert "trades_prior_positions" in stats
    finally:
        api_main._rules_state.set_rules(original_rules)
