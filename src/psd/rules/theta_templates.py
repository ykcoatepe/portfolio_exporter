"""Theta template selector (v0.1)."""

from __future__ import annotations

from typing import Dict


def pick_by_vix(vix: float) -> Dict[str, float]:
    """Return dte/tp capture band by VIX regime."""
    if vix < 15:
        return {"dte_min": 45, "dte_max": 60, "tp_min": 0.50, "tp_max": 0.70}
    if vix <= 25:
        return {"dte_min": 30, "dte_max": 45, "tp_min": 0.40, "tp_max": 0.60}
    return {"dte_min": 14, "dte_max": 30, "tp_min": 0.30, "tp_max": 0.50}
