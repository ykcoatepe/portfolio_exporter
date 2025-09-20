# SPDX-License-Identifier: MIT

"""Safe evaluation of rule expressions over normalized position rows."""

from __future__ import annotations

import ast
import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from .schema import Breach, Rule, Scope


class RuleParseError(ValueError):
    """Raised when a rule expression fails validation."""


class RuleEvaluationError(RuntimeError):
    """Raised when a rule expression cannot be evaluated."""


_ALLOWED_NODES = (
    ast.Expression,
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.Name,
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.Set,
    ast.Load,
    ast.And,
    ast.Or,
    ast.Not,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.USub,
    ast.UAdd,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Is,
    ast.IsNot,
    ast.In,
    ast.NotIn,
)
_ALLOWED_BOOLOPS = (ast.And, ast.Or)
_ALLOWED_UNARYOPS = (ast.Not, ast.USub, ast.UAdd)
_ALLOWED_BINOPS = (
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
)
_ALLOWED_CMPOPS = (
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Is,
    ast.IsNot,
    ast.In,
    ast.NotIn,
)

# Default values for optional identifiers so expressions can evaluate even when
# a particular snapshot does not expose the metric. These defaults skew toward
# the "no breach" side for protective rules and ensure filters short‑circuit
# cleanly without tripping `Unknown identifier` errors during catalog
# validation.
_DEFAULT_IDENTIFIER_VALUES: dict[str, Any] = {
    "all_legs_present": False,
    "ask": 0.0,
    "baseline_size_pct": 1.0,
    "bid": 0.0,
    "bucket": "",
    "day_pnl_nav_pct": -100.0,
    "delta_beta": 0.0,
    "float_millions": 1000.0,
    "has_macro_event_tag": False,
    "has_naked_short": False,
    "has_stop": False,
    "has_target": False,
    "is_borrowable": False,
    "is_defined_risk": False,
    "iv": None,
    "liquidity_nav_pct": 0.0,
    "margin_used_pct": 100.0,
    "microcap_nav_pct": 999.0,
    "month_dd_nav_pct": -100.0,
    "naked_short_hedged": False,
    "new_risk_halted": False,
    "next_earnings_within_dte": False,
    "opened_within_days": 999,
    "options_theta_nav_pct": 999.0,
    "pct_cut_top_var": 0.0,
    "position_size_pct": 999.0,
    "premarket_gap_pct": 0.0,
    "rvol": 0.0,
    "strategy": "",
    "sum_delta": 0.0,
    "trade_nav_pct": 999.0,
    "trading_frozen_1d": False,
    "ul_nav_pct": 999.0,
    "var95_1d_pct": 1.0,
    "vix": 999.0,
}


@dataclass(slots=True)
class _CompiledExpression:
    source: str
    node: ast.expr | None


@dataclass(slots=True)
class EvaluationResult:
    breaches: list[Breach]
    rules_evaluated: int
    duration_ms: float


def evaluate_rules(
    rules: Sequence[Rule],
    rows_by_scope: Mapping[Scope, Iterable[Mapping[str, Any]]],
    *,
    as_of: datetime | None = None,
) -> EvaluationResult:
    """Evaluate a collection of rules against normalized rows.

    Parameters
    ----------
    rules:
        Rules to evaluate.
    rows_by_scope:
        Mapping from rule scope to iterables of rows. Rows are expected to
        expose identifiers used by the expressions as top-level keys.
    as_of:
        Timestamp used when rows do not declare their own ``triggered_at``.
    """

    started = perf_counter()
    evaluation_ts = _ensure_aware(as_of or datetime.now(tz=UTC))
    compiled: list[tuple[Rule, _CompiledExpression, _CompiledExpression]] = []
    for rule in rules:
        if not rule.enabled:
            continue
        compiled.append((rule, _compile(rule.filter), _compile(rule.expr)))

    materialized_rows: dict[Scope, list[Mapping[str, Any]]] = {}
    for scope, rows in rows_by_scope.items():
        if isinstance(rows, list):
            materialized_rows[scope] = rows
        else:
            materialized_rows[scope] = list(rows)

    breaches: list[Breach] = []
    for rule, filter_expr, match_expr in compiled:
        rows = materialized_rows.get(rule.scope, [])
        for raw_row in rows:
            row = dict(raw_row)
            context = _build_context(row)
            if filter_expr.node is not None:
                if not _to_bool(_evaluate(filter_expr.node, context)):
                    continue
            if not match_expr.node:
                raise RuleParseError(f"Rule {rule.rule_id} has empty expr")
            result = _evaluate(match_expr.node, context)
            if not isinstance(result, bool):
                raise RuleEvaluationError(
                    f"Rule {rule.rule_id} expression must return bool, got {type(result)!r}"
                )
            if not result:
                continue
            triggered_at = _resolve_triggered_at(row.get("triggered_at"), evaluation_ts)
            subject_id = _subject_id(row)
            symbol = row.get("symbol")
            value = _extract_value(row)
            notes = _extract_notes(row)
            breach_id = _breach_id(rule, triggered_at, subject_id)
            breaches.append(
                Breach(
                    breach_id=breach_id,
                    rule_id=rule.rule_id,
                    scope=rule.scope,
                    subject_id=subject_id,
                    symbol=symbol,
                    triggered_at=triggered_at,
                    value=value,
                    status=row.get("status", "OPEN"),
                    notes=notes,
                )
            )

    duration_ms = (perf_counter() - started) * 1000.0
    return EvaluationResult(breaches=breaches, rules_evaluated=len(compiled), duration_ms=duration_ms)


def _compile(source: str) -> _CompiledExpression:
    if not source or not source.strip():
        return _CompiledExpression(source=source, node=None)
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as exc:  # pragma: no cover - defensive
        raise RuleParseError(f"Invalid expression: {source!r}") from exc
    expr = tree.body
    _validate_expr(expr)
    return _CompiledExpression(source=source, node=expr)


def _validate_expr(node: ast.AST) -> None:
    for child in ast.walk(node):
        if isinstance(child, (ast.Call, ast.Attribute, ast.Subscript, ast.Await, ast.Lambda)):
            raise RuleParseError("Function calls, attributes, and subscripts are not allowed")
        if not isinstance(child, _ALLOWED_NODES):
            raise RuleParseError(f"Disallowed expression node: {type(child).__name__}")
        if isinstance(child, ast.BoolOp) and not isinstance(child.op, _ALLOWED_BOOLOPS):
            raise RuleParseError("Only 'and'/'or' boolean operators are supported")
        if isinstance(child, ast.UnaryOp) and not isinstance(child.op, _ALLOWED_UNARYOPS):
            raise RuleParseError("Only not/+/- unary operators are supported")
        if isinstance(child, ast.BinOp) and not isinstance(child.op, _ALLOWED_BINOPS):
            raise RuleParseError("Unsupported binary operator")
        if isinstance(child, ast.Compare):
            if any(not isinstance(op, _ALLOWED_CMPOPS) for op in child.ops):
                raise RuleParseError("Unsupported comparison operator")
        if isinstance(child, ast.Name) and child.id.startswith("__"):
            raise RuleParseError("Names starting with '__' are not allowed")
        if isinstance(child, ast.Constant) and isinstance(child.value, complex):
            raise RuleParseError("Complex literals are not allowed")


def _evaluate(node: ast.AST, context: Mapping[str, Any]) -> Any:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body, context)
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            for value in node.values:
                if not _to_bool(_evaluate(value, context)):
                    return False
            return True
        if isinstance(node.op, ast.Or):
            for value in node.values:
                if _to_bool(_evaluate(value, context)):
                    return True
            return False
        raise RuleEvaluationError("Unsupported boolean operator")
    if isinstance(node, ast.UnaryOp):
        operand = _evaluate(node.operand, context)
        if isinstance(node.op, ast.Not):
            return not _to_bool(operand)
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.UAdd):
            return +operand
        raise RuleEvaluationError("Unsupported unary operator")
    if isinstance(node, ast.BinOp):
        left = _evaluate(node.left, context)
        right = _evaluate(node.right, context)
        op = node.op
        if isinstance(op, ast.Add):
            return left + right
        if isinstance(op, ast.Sub):
            return left - right
        if isinstance(op, ast.Mult):
            return left * right
        if isinstance(op, ast.Div):
            return left / right
        if isinstance(op, ast.FloorDiv):
            return left // right
        if isinstance(op, ast.Mod):
            return left % right
        if isinstance(op, ast.Pow):
            return left**right
        raise RuleEvaluationError("Unsupported binary operator")
    if isinstance(node, ast.Compare):
        left = _evaluate(node.left, context)
        for operator, comparator in zip(node.ops, node.comparators, strict=True):
            right = _evaluate(comparator, context)
            matched = _compare(operator, left, right)
            if not matched:
                return False
            left = right
        return True
    if isinstance(node, ast.Name):
        if node.id in {"True", "true"}:
            return True
        if node.id in {"False", "false"}:
            return False
        if node.id in {"None", "null"}:
            return None
        if node.id not in context:
            if node.id in _DEFAULT_IDENTIFIER_VALUES:
                return _DEFAULT_IDENTIFIER_VALUES[node.id]
            raise RuleEvaluationError(f"Unknown identifier: {node.id}")
        return context[node.id]
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.List):
        return [_evaluate(elt, context) for elt in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_evaluate(elt, context) for elt in node.elts)
    if isinstance(node, ast.Set):
        return {_evaluate(elt, context) for elt in node.elts}
    raise RuleEvaluationError(f"Unsupported expression node: {type(node).__name__}")


def _compare(operator: ast.cmpop, left: Any, right: Any) -> bool:
    if isinstance(operator, ast.Eq):
        return left == right
    if isinstance(operator, ast.NotEq):
        return left != right
    if isinstance(operator, ast.Lt):
        return left < right
    if isinstance(operator, ast.LtE):
        return left <= right
    if isinstance(operator, ast.Gt):
        return left > right
    if isinstance(operator, ast.GtE):
        return left >= right
    if isinstance(operator, ast.Is):
        return left is right
    if isinstance(operator, ast.IsNot):
        return left is not right
    if isinstance(operator, ast.In):
        return left in right
    if isinstance(operator, ast.NotIn):
        return left not in right
    raise RuleEvaluationError("Unsupported comparison operator")


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return bool(value)


def _build_context(row: Mapping[str, Any]) -> dict[str, Any]:
    context: dict[str, Any] = dict(_DEFAULT_IDENTIFIER_VALUES)
    for key, value in row.items():
        if isinstance(key, str) and key.isidentifier() and not key.startswith("__"):
            context[key] = value
    return context


def _subject_id(row: Mapping[str, Any]) -> str:
    for key in ("subject_id", "id", "symbol"):
        value = row.get(key)
        if value is not None:
            return str(value)
    raise RuleEvaluationError("Row is missing subject identifier")


def _extract_value(row: Mapping[str, Any]) -> float | None:
    value = row.get("value")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise RuleEvaluationError("Value must be numeric if provided") from None


def _extract_notes(row: Mapping[str, Any]) -> str | None:
    notes = row.get("notes")
    if notes is None:
        return None
    return str(notes)


def _breach_id(rule: Rule, triggered_at: datetime, subject_id: str) -> str:
    key = f"PSD|{rule.rule_id}|{rule.scope}|{subject_id}|{triggered_at.isoformat()}"
    digest = hashlib.sha1(key.encode("utf-8"), usedforsecurity=False)
    return digest.hexdigest()


def _ensure_aware(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC)


def _resolve_triggered_at(raw_ts: Any, fallback: datetime) -> datetime:
    if raw_ts is None:
        return fallback
    if isinstance(raw_ts, datetime):
        return _ensure_aware(raw_ts)
    if isinstance(raw_ts, str):
        text = raw_ts.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return _ensure_aware(datetime.fromisoformat(text))
        except ValueError as exc:  # pragma: no cover - defensive
            raise RuleEvaluationError("triggered_at must be ISO timestamp") from exc
    raise RuleEvaluationError("triggered_at must be datetime or ISO string")
