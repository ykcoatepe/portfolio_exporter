# SPDX-License-Identifier: MIT

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from positions_engine.rules import Rule, evaluate_rules
from positions_engine.rules.eval import RuleParseError


def _ts() -> datetime:
    return datetime(2025, 9, 19, 9, 0, tzinfo=UTC)


def test_combo_premium_rule_emits_breach() -> None:
    rules = [
        Rule(
            rule_id="combo_high",
            name="High premium combo",
            severity="CRITICAL",
            scope="COMBO",
            filter="dte <= 7",
            expr="annualized_premium_pct >= 30",
        )
    ]
    rows = {
        "COMBO": [
            {
                "subject_id": "combo-1",
                "symbol": "TSLA",
                "dte": 6,
                "annualized_premium_pct": 42.1,
                "value": 42.1,
                "triggered_at": _ts(),
            }
        ]
    }

    result = evaluate_rules(rules, rows, as_of=_ts())

    assert len(result.breaches) == 1
    breach = result.breaches[0]
    assert breach.rule_id == "combo_high"
    assert breach.scope == "COMBO"
    assert breach.value == pytest.approx(42.1)


def test_leg_iv_missing_triggers_warning() -> None:
    rules = [
        Rule(
            rule_id="leg_iv_missing",
            name="IV missing",
            severity="WARNING",
            scope="LEG",
            filter="dte <= 5",
            expr="iv is None",
        )
    ]
    rows = {
        "LEG": [
            {
                "subject_id": "leg-1",
                "symbol": "TSLA230920C",
                "dte": 3,
                "iv": None,
                "triggered_at": _ts(),
            }
        ]
    }

    result = evaluate_rules(rules, rows, as_of=_ts())

    assert len(result.breaches) == 1
    breach = result.breaches[0]
    assert breach.rule_id == "leg_iv_missing"
    assert breach.scope == "LEG"
    assert breach.symbol == "TSLA230920C"


def test_leg_staleness_triggers_multiple_rules() -> None:
    rules = [
        Rule(
            rule_id="leg_warning",
            name="Leg stale warning",
            severity="WARNING",
            scope="LEG",
            filter="",
            expr="stale_seconds > 600",
        ),
        Rule(
            rule_id="leg_critical",
            name="Leg stale critical",
            severity="CRITICAL",
            scope="LEG",
            filter="",
            expr="stale_seconds > 900",
        ),
    ]
    rows = {
        "LEG": [
            {
                "subject_id": "leg-2",
                "symbol": "TSLA230920C",
                "dte": 4,
                "stale_seconds": 1200,
                "triggered_at": _ts(),
            }
        ]
    }

    result = evaluate_rules(rules, rows, as_of=_ts())

    assert {breach.rule_id for breach in result.breaches} == {"leg_warning", "leg_critical"}


def test_expression_rejects_dangerous_strings() -> None:
    rules = [
        Rule(
            rule_id="bad",
            name="invalid",
            severity="INFO",
            scope="PORT",
            filter="",
            expr="__import__('os')",
        )
    ]

    with pytest.raises(RuleParseError):
        evaluate_rules(rules, {"PORT": []}, as_of=_ts())
