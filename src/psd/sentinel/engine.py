"""Sentinel engine (v0.1)."""

from __future__ import annotations

import time
from typing import Any, Dict, List

from ..models import Alert, Position, RiskSnapshot
from ..analytics.exposure import delta_beta_exposure
from ..analytics.var import var95_1d_from_closes
from ..analytics.combos import group_credit_spreads
from ..datasources import ibkr as ib_src, yfin as yf_src
from ..rules import risk_bands, circuit_breakers, theta_templates, universal
from .memos import write_jsonl


def _now_ts() -> int:
    return int(time.time())


def scan_once(cfg: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Run a single scan and return a DTO for CLI rendering.

    The result contains: snapshot, alerts, rows (for CLI table).
    """
    cfg = cfg or {}
    nav = float(cfg.get("nav", 100_000.0))
    memo_path = cfg.get("memo_path", "var/memos/psd_memos.jsonl")

    positions: List[Position] = []
    # Datasource integration is mocked in tests; default empty
    for row in ib_src.get_positions(cfg):
        try:
            positions.append(row if isinstance(row, Position) else Position(**row))
        except Exception:
            continue

    vix = yf_src.get_vix(cfg) or 20.0
    # Exposure and VaR
    d_beta = delta_beta_exposure(positions, nav)
    closes = yf_src.get_closes("SPY", 60, cfg)
    var_abs = var95_1d_from_closes(closes, nav * abs(d_beta)) if closes else 0.0
    margin_used = float(cfg.get("margin_used", 0.0))
    snapshot = RiskSnapshot(nav=nav, vix=vix, delta_beta=d_beta, var95_1d=var_abs, margin_used=margin_used)

    # Evaluate bands and breakers (toy daily_return and var_change from cfg)
    band_key, breaches = risk_bands.evaluate(vix, d_beta, var_abs / nav if nav else 0.0, margin_used)
    daily_ret = float(cfg.get("daily_return", 0.0))
    var_change = float(cfg.get("var_change", 0.0))
    breakers = circuit_breakers.evaluate(daily_ret, var_change)

    # Group combos (no-op v0.1)
    positions2 = group_credit_spreads(positions)

    # Build alerts and rows
    alerts: List[Alert] = []
    rows: List[Dict[str, Any]] = []
    for p in positions2:
        one_r = universal.compute_1r(p.qty, p.mark)
        stop, target = universal.oco_levels(p.mark, one_r, -1.0, 2.0)
        msg = ""
        severity = "info"
        if any(breaches.values()) or any(breakers.values()):
            severity = "warn"
            msg = ",".join(k for k, v in {**breaches, **breakers}.items() if v)
        alerts.append(Alert(uid=p.uid, rule="oco", severity=severity, message=msg))
        rows.append(
            {
                "uid": p.uid,
                "sleeve": p.sleeve,
                "kind": p.kind,
                "R": round(one_r, 2),
                "stop": round(stop, 2),
                "target": round(target, 2),
                "mark": round(p.mark, 2),
                "alert": msg or "",
            }
        )

    # Write memos
    ts = _now_ts()
    for a in alerts:
        write_jsonl(
            memo_path,
            {
                "ts": ts,
                "uid": a.uid,
                "rule": a.rule,
                "severity": a.severity,
                "snapshot": {
                    "nav": snapshot.nav,
                    "vix": snapshot.vix,
                    "delta_beta": snapshot.delta_beta,
                    "var95_1d": snapshot.var95_1d,
                    "band": band_key,
                },
                "suggestion": a.message or None,
            },
        )

    return {
        "snapshot": {
            "nav": snapshot.nav,
            "vix": snapshot.vix,
            "delta_beta": snapshot.delta_beta,
            "var95_1d": snapshot.var95_1d,
            "band": band_key,
            "breaches": breaches,
            "breakers": breakers,
        },
        "alerts": [a.__dict__ for a in alerts],
        "rows": rows,
    }
