"""Sentinel engine (v0.1)."""

from __future__ import annotations

import time
from typing import Any, Dict, List

from ..models import Alert, Position, RiskSnapshot
from ..analytics.exposure import delta_beta_exposure
from ..analytics.var import var95_1d_from_closes
from ..analytics.combos import recognize
from ..datasources import ibkr as ib_src, yfin as yf_src
from ..rules import risk_bands, circuit_breakers, theta_templates, universal
from ..rules import budgets as budget_rules
from ..analytics.kpis import per_sleeve_kpis
from .memos import write_jsonl, write_digest


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
    breaker_state = circuit_breakers.derive_state(float(cfg.get("day_pl", daily_ret)), float(cfg.get("month_pl", 0.0)))

    # Recognize combos (spreads/condors) and orphan risk
    combos, orphans = recognize(positions)

    # Build alerts and rows
    alerts: List[Alert] = []
    rows: List[Dict[str, Any]] = []
    # Leg-level alerts suppressed; evaluate at combo-level
    combo_debits: Dict[str, float] = cfg.get("combo_debits", {}) if isinstance(cfg.get("combo_debits"), dict) else {}
    for c in combos:
        uid = f"{c.symbol}-{c.expiry}-{c.kind}"
        debit_now = float(combo_debits.get(uid, max(0.0, c.credit * 0.5)))
        sev, reason = theta_templates.enforce(vix, c.dte, max(c.credit, 0.0), debit_now)
        if any(breaches.values()) or any(breakers.values()):
            sev = "warn" if sev == "info" else sev
            reason = ",".join(k for k, v in {**breaches, **breakers}.items() if v) or reason
        alerts.append(Alert(uid=uid, rule="combo", severity=sev, message=reason))
        rows.append(
            {
                "uid": uid,
                "sleeve": "theta",
                "kind": c.kind,
                "R": round(c.max_loss, 2),
                "stop": "-",
                "target": "-",
                "mark": round(c.credit, 2),
                "alert": reason or "",
            }
        )
    for o in orphans:
        uid = f"{o['symbol']}-{o['expiry']}-orphan-{o['side']}"
        alerts.append(Alert(uid=uid, rule="orphan", severity="warn", message=o.get("reason", "orphan-risk")))
        rows.append({"uid": uid, "sleeve": "theta", "kind": "orphan", "R": 0, "stop": "-", "target": "-", "mark": 0, "alert": o.get("reason", "")})

    # Budgets footer
    fees_wtd = float(cfg.get("theta_fees_wtd", 0.0))
    hedge_mtd = float(cfg.get("hedge_cost_mtd", 0.0))
    thresholds = (cfg.get("budgets") if isinstance(cfg.get("budgets"), dict) else {})
    budgets_dto = budget_rules.footer_dto(nav, fees_wtd, hedge_mtd, thresholds)

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

    # Rollup digest (30m or adhoc)
    if cfg.get("rollup_digest"):
        summary = {
            "ts": ts,
            "band": band_key,
            "breaker_state": breaker_state,
            "counts": {
                "alerts": len(alerts),
                "warn": sum(1 for a in alerts if a.severity == "warn"),
                "action": sum(1 for a in alerts if a.severity == "action"),
            },
            "breaches": {k: v for k, v in breaches.items() if v},
            "budgets": budgets_dto,
        }
        write_digest(memo_path, "digest_rollup", summary)

    # Optional EOD digest
    if cfg.get("eod_digest"):
        # For tests, feed kpi_memos via cfg; otherwise keep light
        kpi_memos = cfg.get("kpi_memos", [])
        kpis = per_sleeve_kpis(kpi_memos) if isinstance(kpi_memos, list) else {}
        write_digest(
            memo_path,
            "digest_eod",
            {
                "ts": ts,
                "kpis": kpis,
                "breaker_state": breaker_state,
                "budgets": budgets_dto,
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
            "breaker_state": breaker_state,
            "margin_used": margin_used,
        },
        "budgets": budgets_dto,
        "alerts": [a.__dict__ for a in alerts],
        "rows": rows,
    }
