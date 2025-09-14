"""Theta template enforcement (v0.2)."""

from __future__ import annotations

from typing import Dict, Tuple


def pick_by_vix(vix: float) -> Dict[str, float]:
    """Return dte/tp capture band by VIX regime."""
    if vix < 15:
        return {"dte_min": 45, "dte_max": 60, "tp_min": 0.50, "tp_max": 0.70}
    if vix <= 25:
        return {"dte_min": 30, "dte_max": 45, "tp_min": 0.40, "tp_max": 0.60}
    return {"dte_min": 14, "dte_max": 30, "tp_min": 0.30, "tp_max": 0.50}


def enforce(vix: float, dte: int, credit: float, debit_now: float) -> Tuple[str, str]:
    """Return (severity, reason) based on regime window and capture percent.

    severity: 'action' (take profit), 'warn' (out-of-template), 'info' otherwise.
    capture% = 1 - debit/credit; compared against regime tp bands.
    """
    tpl = pick_by_vix(vix)
    if dte < int(tpl["dte_min"]) or dte > int(tpl["dte_max"]):
        return "warn", "out-of-template"
    if credit <= 0:
        return "info", ""
    capture = 1.0 - float(debit_now) / float(credit)
    # v0.2: action when capture hits lower band or above
    if capture >= float(tpl["tp_min"]):
        return "action", "tp"
    return "info", ""


def theta_fees_warn(weekly_fees_abs: float, nav: float, threshold_nav_frac: float | None = None) -> bool:
    """Warn when weekly theta fees exceed a NAV fraction.

    threshold_nav_frac defaults to 0.20% (0.002) if not provided. Make this
    configurable via rules.yaml (per regime or global), if available upstream.
    """
    if nav <= 0:
        return False
    t = 0.002 if threshold_nav_frac is None else float(threshold_nav_frac)
    return (weekly_fees_abs / nav) > t
