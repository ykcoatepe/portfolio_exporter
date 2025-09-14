"""Circuit breaker evaluation (v0.3)."""

from __future__ import annotations

from typing import Dict, List, Tuple


def evaluate(daily_return: float, var_change: float) -> Dict[str, bool]:
    """Return breaker states using v0.1 defaults.

    - soft_pre at -1.0%
    - freeze_1d at -1.5%
    - cut_var at -2.5% or worsening VaR change
    """
    soft_pre = daily_return <= -0.010
    freeze_1d = daily_return <= -0.015
    cut_var = daily_return <= -0.025 or var_change < 0
    return {"soft_pre": soft_pre, "freeze_1d": freeze_1d, "cut_var": cut_var}


def derive_state(day_pl: float, month_pl: float, thresholds: Dict[str, float] | None = None) -> Dict[str, str]:
    """Derive breaker state from day/month P&L (fractions).

    thresholds: {soft_pre: -0.010, freeze_1d: -0.015, cut_var: -0.025}
    Returns {state: ok|soft_pre|freeze_1d|cut_var, reason: "..."}
    """
    t = thresholds or {"soft_pre": -0.010, "freeze_1d": -0.015, "cut_var": -0.025}
    if day_pl <= float(t.get("cut_var", -0.025)):
        return {"state": "cut_var", "reason": f"day {day_pl:.2%} <= {t.get('cut_var'):.2%}"}
    if day_pl <= float(t.get("freeze_1d", -0.015)):
        return {"state": "freeze_1d", "reason": f"day {day_pl:.2%} <= {t.get('freeze_1d'):.2%}"}
    if day_pl <= float(t.get("soft_pre", -0.010)):
        return {"state": "soft_pre", "reason": f"day {day_pl:.2%} <= {t.get('soft_pre'):.2%}"}
    return {"state": "ok", "reason": ""}


def produce_actions(risk_snapshot: Dict[str, object], top_frac: float = 0.15) -> List[str]:
    """Produce suggested trims under cut_var: top-15% VaR names.

    risk_snapshot may contain key 'by_symbol_var' -> list of {symbol, var}.
    Returns list of symbol identifiers to trim.
    """
    rows = []
    try:
        rows = list(risk_snapshot.get("by_symbol_var", []))  # type: ignore[arg-type]
    except Exception:
        rows = []
    if not rows:
        return []
    xs = sorted([r for r in rows if isinstance(r, dict) and "symbol" in r and "var" in r], key=lambda r: float(r.get("var", 0.0)), reverse=True)
    if not xs:
        return []
    n = max(1, int(len(xs) * max(0.0, min(top_frac, 1.0))))
    return [str(r["symbol"]) for r in xs[:n]]
