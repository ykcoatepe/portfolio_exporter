# SPDX-License-Identifier: MIT

"""Rules evaluation state built on top of :class:`PositionsState`."""

from __future__ import annotations

import importlib.resources as resources
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from ..combos.detector import OptionCombo, OptionLegSnapshot
from ..rules import EvaluationResult, Rule, evaluate_rules
from ..rules.schema import Scope
from .state import PositionsState

_SEVERITY_ORDER = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}

_DEFAULT_RULES_FALLBACK: list[dict[str, Any]] = [
    {
        "rule_id": "combo__annualized_premium_high",
        "name": "Annualized premium >=30% within a week",
        "severity": "CRITICAL",
        "scope": "COMBO",
        "filter": "dte <= 7",
        "expr": "annualized_premium_pct >= 30",
    },
    {
        "rule_id": "ul__delta_extreme",
        "name": "Underlying delta beyond +-1.2",
        "severity": "WARNING",
        "scope": "UL",
        "filter": "",
        "expr": "delta > 1.2 or delta < -1.2",
    },
    {
        "rule_id": "port__theta_negative",
        "name": "Portfolio net theta is negative",
        "severity": "INFO",
        "scope": "PORT",
        "filter": "",
        "expr": "net_theta_per_day < 0",
    },
    {
        "rule_id": "leg__iv_missing_near_term",
        "name": "Missing IV for near-term legs",
        "severity": "WARNING",
        "scope": "LEG",
        "filter": "dte <= 5",
        "expr": "iv is None",
    },
    {
        "rule_id": "leg__mark_stale",
        "name": "Option mark stale > 15 minutes",
        "severity": "CRITICAL",
        "scope": "LEG",
        "filter": "",
        "expr": "stale_seconds > 900",
    },
]


class RulesState:
    """Evaluate configured rules against the current positions snapshot."""

    def __init__(self, positions_state: PositionsState, rules: Sequence[Rule] | None = None) -> None:
        self._positions_state = positions_state
        self._rules: tuple[Rule, ...] = tuple(rules) if rules is not None else tuple(_load_default_rules())
        self._severity_by_rule = {rule.rule_id: rule.severity for rule in self._rules}

    @property
    def rules(self) -> tuple[Rule, ...]:
        return self._rules

    def set_rules(self, rules: Sequence[Rule]) -> None:
        self._rules = tuple(rules)
        self._severity_by_rule = {rule.rule_id: rule.severity for rule in self._rules}

    def reload_examples(self) -> None:
        self.set_rules(_load_default_rules())

    def evaluate(self, now: datetime | None = None) -> EvaluationResult:
        timestamp = _ensure_aware(now)
        rows = self._build_rows(timestamp)
        return evaluate_rules(self._rules, rows, as_of=timestamp)

    def summary(self, now: datetime | None = None) -> tuple[dict[str, Any], EvaluationResult]:
        timestamp = _ensure_aware(now)
        result = self.evaluate(timestamp)
        summary = {
            "as_of": _isoformat(timestamp),
            "rules_total": len(self._rules),
            "breaches": self._breach_counters(result.breaches),
            "top": self._top_breaches(result.breaches),
        }
        return summary, result

    def _breach_counters(self, breaches: Sequence[Any]) -> dict[str, int]:
        totals = {"critical": 0, "warning": 0, "info": 0}
        for breach in breaches:
            severity = self._severity_by_rule.get(breach.rule_id, "INFO")
            if severity == "CRITICAL":
                totals["critical"] += 1
            elif severity == "WARNING":
                totals["warning"] += 1
            else:
                totals["info"] += 1
        return totals

    def _top_breaches(self, breaches: Sequence[Any]) -> list[dict[str, Any]]:
        ordered = sorted(
            breaches,
            key=lambda breach: (
                _SEVERITY_ORDER.get(self._severity_by_rule.get(breach.rule_id, "INFO"), 99),
                -breach.triggered_at.timestamp(),
            ),
        )
        top: list[dict[str, Any]] = []
        for breach in ordered[:5]:
            payload = breach.model_dump(mode="json") if hasattr(breach, "model_dump") else dict(breach)
            top.append(payload)
        return top

    def _build_rows(self, now: datetime) -> Mapping[Scope, Iterable[Mapping[str, Any]]]:
        equities = self._positions_state.equities_payload(now)
        equities_by_symbol = {row.get("symbol"): row for row in equities if row.get("symbol")}
        detection = self._positions_state.options_detection(now)
        combos = detection.combos
        orphan_legs = list(detection.orphans)
        combo_legs: list[OptionLegSnapshot] = [leg for combo in combos for leg in combo.legs]
        all_legs = combo_legs + orphan_legs

        rows: dict[Scope, list[dict[str, Any]]] = {
            "COMBO": self._combo_rows(combos, equities_by_symbol, now),
            "LEG": self._leg_rows(all_legs, now),
            "UL": self._underlying_rows(combos, orphan_legs, equities, now),
            "PORT": self._portfolio_rows(combos, orphan_legs, now),
        }
        return rows

    def _combo_rows(
        self,
        combos: Sequence[OptionCombo],
        equities_by_symbol: Mapping[str | None, Mapping[str, Any]],
        now: datetime,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for combo in combos:
            mark = _to_float(equities_by_symbol.get(combo.underlying, {}).get("mark"))
            annualized_pct = _annualized_premium_pct(combo, mark)
            notes = None
            if annualized_pct is not None:
                notes = f"annualized premium {annualized_pct:.1f}%"
            rows.append(
                {
                    "subject_id": combo.combo_id,
                    "symbol": combo.underlying,
                    "dte": combo.dte,
                    "annualized_premium_pct": annualized_pct,
                    "value": annualized_pct,
                    "triggered_at": now,
                    "notes": notes,
                }
            )
        return rows

    def _leg_rows(self, legs: Sequence[OptionLegSnapshot], now: datetime) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for leg in legs:
            notes_parts: list[str] = []
            if leg.iv is None:
                notes_parts.append("iv missing")
            if leg.stale_seconds:
                notes_parts.append(f"stale {leg.stale_seconds}s")
            notes = ", ".join(notes_parts) if notes_parts else None
            rows.append(
                {
                    "subject_id": leg.leg_id,
                    "symbol": leg.instrument_symbol,
                    "dte": leg.dte,
                    "iv": _to_float(leg.iv),
                    "stale_seconds": leg.stale_seconds,
                    "value": leg.stale_seconds,
                    "triggered_at": now,
                    "notes": notes,
                }
            )
        return rows

    def _underlying_rows(
        self,
        combos: Sequence[OptionCombo],
        orphan_legs: Sequence[OptionLegSnapshot],
        equities: Sequence[Mapping[str, Any]],
        now: datetime,
    ) -> list[dict[str, Any]]:
        aggregates: dict[str, dict[str, float]] = defaultdict(
            lambda: {"delta_shares": 0.0, "gross_shares": 0.0}
        )
        for combo in combos:
            entry = aggregates[combo.underlying]
            entry["delta_shares"] += _decimal_to_float(combo.sum_delta)
            entry["gross_shares"] += sum(
                abs(_decimal_to_float(leg.quantity * leg.multiplier)) for leg in combo.legs
            )
        for leg in orphan_legs:
            entry = aggregates[leg.underlying]
            if leg.delta is not None:
                entry["delta_shares"] += _decimal_to_float(leg.delta * leg.quantity * leg.multiplier)
            entry["gross_shares"] += abs(_decimal_to_float(leg.quantity * leg.multiplier))
        for equity in equities:
            symbol = equity.get("symbol")
            if not symbol:
                continue
            qty = float(equity.get("qty", 0.0))
            if qty == 0:
                continue
            entry = aggregates[symbol]
            entry["delta_shares"] += qty
            entry["gross_shares"] += abs(qty)

        rows: list[dict[str, Any]] = []
        for symbol, values in aggregates.items():
            gross = values["gross_shares"]
            if gross <= 0:
                continue
            delta_ratio = values["delta_shares"] / gross
            rows.append(
                {
                    "subject_id": symbol,
                    "symbol": symbol,
                    "delta": delta_ratio,
                    "value": delta_ratio,
                    "triggered_at": now,
                    "notes": f"Δ {delta_ratio:.2f}",
                }
            )
        return rows

    def _portfolio_rows(
        self,
        combos: Sequence[OptionCombo],
        orphan_legs: Sequence[OptionLegSnapshot],
        now: datetime,
    ) -> list[dict[str, Any]]:
        theta_total = sum(_decimal_to_float(combo.sum_theta) for combo in combos)
        for leg in orphan_legs:
            if leg.theta is None:
                continue
            theta_total += _decimal_to_float(leg.theta * leg.quantity * leg.multiplier)
        notes = f"net θ/day {theta_total:.2f}"
        return [
            {
                "subject_id": "PORT",
                "net_theta_per_day": theta_total,
                "value": theta_total,
                "triggered_at": now,
                "notes": notes,
            }
        ]


def _load_default_rules() -> list[Rule]:
    data: list[dict[str, Any]] | None = None
    try:
        import yaml  # type: ignore[import]
    except ModuleNotFoundError:  # pragma: no cover - import guard
        yaml = None  # type: ignore[assignment]
    if yaml is not None:
        try:
            with (
                resources.files("positions_engine.rules")
                .joinpath("examples.yaml")
                .open("r", encoding="utf-8") as handle
            ):
                loaded = yaml.safe_load(handle) or []
        except FileNotFoundError:  # pragma: no cover - defensive
            loaded = []
        if isinstance(loaded, list):
            data = loaded
    if data is None:
        data = _DEFAULT_RULES_FALLBACK
    return [Rule.model_validate(item) for item in data]


def _ensure_aware(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(tz=UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _isoformat(ts: datetime) -> str:
    text = ts.astimezone(UTC).isoformat()
    if text.endswith("+00:00"):
        return text[:-6] + "Z"
    return text


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, float):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return None


def _decimal_to_float(value: Decimal | float | int) -> float:
    return float(value)


def _annualized_premium_pct(combo: OptionCombo, underlying_mark: float | None) -> float | None:
    if combo.dte <= 0 or underlying_mark is None or underlying_mark <= 0:
        return None
    if not combo.legs:
        return None
    multiplier = abs(_decimal_to_float(combo.legs[0].multiplier)) or 1.0
    premium_value = _decimal_to_float(combo.net_price) * multiplier
    notional = underlying_mark * multiplier
    if notional == 0:
        return None
    ratio = premium_value / abs(notional)
    annualized = ratio * (365.0 / combo.dte) * 100.0
    return annualized
