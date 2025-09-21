from __future__ import annotations

"""Toy KPI aggregation (v0.3). Pure and fast for tests.

Inputs: list of memo-like dicts with optional keys:
  - sleeve: str
  - R: float (per-trade R multiple)
  - win: bool
  - theta_roc: float (per-period return on capital)
  - cost: float (fees/costs absolute)
  - nav: float (optional for cost%)
"""

from collections.abc import Iterable


def _safe_float(x) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0


def per_sleeve_kpis(memos: Iterable[dict]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    agg: dict[str, dict[str, float]] = {}
    cnt: dict[str, dict[str, int]] = {}
    for m in memos:
        s = str(m.get("sleeve", "")).strip() or "unknown"
        a = agg.setdefault(s, {"R_sum": 0.0, "theta_roc_sum": 0.0, "cost_sum": 0.0, "nav_sum": 0.0})
        c = cnt.setdefault(s, {"N": 0, "wins": 0})
        R = _safe_float(m.get("R"))
        a["R_sum"] += R
        a["theta_roc_sum"] += _safe_float(m.get("theta_roc"))
        a["cost_sum"] += _safe_float(m.get("cost"))
        a["nav_sum"] += _safe_float(m.get("nav"))
        c["N"] += 1
        if bool(m.get("win")):
            c["wins"] += 1
    for s in agg:
        N = max(1, cnt[s]["N"])
        win_rate = cnt[s]["wins"] / N
        avg_R = agg[s]["R_sum"] / N
        theta_ROC = agg[s]["theta_roc_sum"] / N
        costs_pct = (agg[s]["cost_sum"] / agg[s]["nav_sum"]) if agg[s]["nav_sum"] > 0 else 0.0
        out[s] = {"win_rate": win_rate, "avg_R": avg_R, "theta_ROC": theta_ROC, "costs_pct": costs_pct}
    return out
