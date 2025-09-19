"""Sentinel engine (v0.1)."""

from __future__ import annotations

import time
from typing import Any

from ..analytics.combos import recognize
from ..analytics.exposure import delta_beta_exposure
from ..analytics.kpis import per_sleeve_kpis
from ..analytics.var import var95_1d_from_closes
from ..datasources import ibkr as ib_src
from ..datasources import yfin as yf_src
from ..models import Alert, OptionLeg, Position, RiskSnapshot
from ..rules import budgets as budget_rules
from ..rules import circuit_breakers, risk_bands, theta_templates
from .memos import write_digest, write_jsonl


def _now_ts() -> int:
    return int(time.time())


# In-memory alert quieting state (per process)
_last_alert_ts: dict[tuple[str, str], int] = {}
_snooze_until: dict[tuple[str, str], int] = {}
_state_loaded: bool = False


def _rebuild_state_from_memos(memo_path: str) -> None:
    """Populate in-memory state from existing memos for continuity after restart.

    - last_alert_ts derives from prior alert memos (entries without explicit type).
    - snooze_until derives from memos with type == 'snooze'.
    """
    global _state_loaded
    try:
        import json

        if not memo_path:
            return
        with open(memo_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                uid = str(obj.get("uid")) if obj.get("uid") is not None else None
                rule = str(obj.get("rule")) if obj.get("rule") is not None else None
                if not uid or not rule:
                    continue
                key = (uid, rule)
                ts = int(obj.get("ts", 0)) if obj.get("ts") is not None else 0
                typ = obj.get("type")
                if typ == "snooze":
                    until = int(obj.get("until", 0)) if obj.get("until") is not None else 0
                    if until > 0:
                        _snooze_until[key] = until
                else:
                    # Treat as an emitted alert memo (engine writes alert memos without 'type')
                    if ts > 0:
                        _last_alert_ts[key] = max(_last_alert_ts.get(key, 0), ts)
        _state_loaded = True
    except FileNotFoundError:
        _state_loaded = True
    except Exception:
        # Best-effort rebuild; ignore errors
        _state_loaded = True


def _load_positions(cfg: dict[str, Any]) -> list[Position]:
    positions: list[Position] = []
    src_positions = cfg.get("positions_override")
    if src_positions is None:
        src_positions = ib_src.get_positions(cfg)
    try:
        iterator = list(src_positions or [])
    except Exception:
        iterator = []
    for row in iterator:
        try:
            pos = row if isinstance(row, Position) else Position(**row)
            if getattr(pos, "legs", None):
                fixed: list[OptionLeg] = []
                for lg in list(pos.legs or []):  # type: ignore[attr-defined]
                    if isinstance(lg, OptionLeg):
                        fixed.append(lg)
                    else:
                        try:
                            fixed.append(OptionLeg(**lg))  # type: ignore[arg-type]
                        except Exception:
                            continue
                pos.legs = fixed  # type: ignore[assignment]
            positions.append(pos)
        except Exception:
            continue
    return positions


def _risk_context(
    positions: list[Position],
    cfg: dict[str, Any],
    nav: float,
) -> tuple[RiskSnapshot, str, dict[str, bool], dict[str, bool], dict[str, str]]:
    vix = yf_src.get_vix(cfg) or 20.0
    d_beta = delta_beta_exposure(positions, nav)
    closes = yf_src.get_closes("SPY", 60, cfg)
    var_abs = var95_1d_from_closes(closes, nav * abs(d_beta)) if closes else 0.0
    margin_used = float(cfg.get("margin_used", 0.0))
    snapshot = RiskSnapshot(nav=nav, vix=vix, delta_beta=d_beta, var95_1d=var_abs, margin_used=margin_used)
    band_key, breaches = risk_bands.evaluate(vix, d_beta, var_abs / nav if nav else 0.0, margin_used)
    daily_ret = float(cfg.get("daily_return", 0.0))
    var_change = float(cfg.get("var_change", 0.0))
    breakers = circuit_breakers.evaluate(daily_ret, var_change)
    breaker_state = circuit_breakers.derive_state(
        float(cfg.get("day_pl", daily_ret)), float(cfg.get("month_pl", 0.0))
    )
    return snapshot, band_key, breaches, breakers, breaker_state


def scan_once(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run a single scan and return a DTO for CLI rendering.

    The result contains: snapshot, alerts, rows (for CLI table).
    """
    cfg = cfg or {}
    nav = float(cfg.get("nav", 100_000.0))
    memo_path = cfg.get("memo_path", "var/memos/psd_memos.jsonl")

    # Optionally rebuild in-memory quieting state from memos on first run
    if not _state_loaded and memo_path:
        _rebuild_state_from_memos(memo_path)

    # Accept runtime snooze commands from cfg: dict or list of dicts
    # {uid, rule, minutes? , until?}
    sno_cmd = cfg.get("snooze")
    if sno_cmd:
        now = _now_ts()
        items = sno_cmd if isinstance(sno_cmd, list) else [sno_cmd]
        for it in items:
            try:
                uid = str(it["uid"])  # required
                rule = str(it.get("rule", "combo"))
            except Exception:
                continue
            minutes = int(it.get("minutes", 0)) if it.get("minutes") is not None else 0
            until = int(it.get("until", 0)) if it.get("until") is not None else 0
            if until <= now:
                until = (
                    now
                    + (minutes if minutes > 0 else int(cfg.get("alerts", {}).get("snooze_default_min", 30)))
                    * 60
                )
            _snooze_until[(uid, rule)] = until
            write_jsonl(
                memo_path,
                {
                    "ts": now,
                    "type": "snooze",
                    "uid": uid,
                    "rule": rule,
                    "until": until,
                    "minutes": minutes or None,
                },
            )

    positions = _load_positions(cfg)
    mark_backfills: list[str] = []
    if hasattr(ib_src, "consume_mark_backfills"):
        try:
            mark_backfills = ib_src.consume_mark_backfills()  # type: ignore[attr-defined]
        except Exception:
            mark_backfills = []
    snapshot, band_key, breaches, breakers, breaker_state = _risk_context(positions, cfg, nav)
    vix = float(snapshot.vix)

    # Recognize combos (spreads/condors) and orphan risk
    combos, orphans = recognize(positions)

    margin_used = snapshot.margin_used or 0.0

    # Build alerts and rows
    alerts: list[Alert] = []
    rows: list[dict[str, Any]] = []
    # Leg-level alerts suppressed; evaluate at combo-level
    combo_debits: dict[str, float] = (
        cfg.get("combo_debits", {}) if isinstance(cfg.get("combo_debits"), dict) else {}
    )
    now_ts = _now_ts()
    debounce_min = 0
    try:
        debounce_min = int((cfg.get("alerts", {}) or {}).get("debounce_min", 5))
    except Exception:
        debounce_min = 5
    debounce_sec = max(0, debounce_min) * 60
    suppressed_now: set[tuple[str, str]] = set()
    for c in combos:
        uid = f"{c.symbol}-{c.expiry}-{c.kind}"
        debit_now = float(combo_debits.get(uid, max(0.0, c.credit * 0.5)))
        sev, reason = theta_templates.enforce(vix, c.dte, max(c.credit, 0.0), debit_now)
        if any(breaches.values()) or any(breakers.values()):
            sev = "warn" if sev == "info" else sev
            reason = ",".join(k for k, v in {**breaches, **breakers}.items() if v) or reason
        key = (uid, "combo")
        # Snooze check
        until = _snooze_until.get(key, 0)
        if until and now_ts < until:
            write_jsonl(
                memo_path,
                {"ts": now_ts, "type": "snoozed", "uid": uid, "rule": "combo", "next": until},
            )
            # Still render the row with a badge
            rows.append(
                {
                    "uid": uid,
                    "sleeve": "theta",
                    "kind": c.kind,
                    "R": round(c.max_loss, 2),
                    "stop": "-",
                    "target": "-",
                    "mark": round(c.credit, 2),
                    "alert": (reason or "") + " [SNOOZED]",
                }
            )
            continue
        # Debounce check
        last = _last_alert_ts.get(key, 0)
        if last and (now_ts - last) < debounce_sec:
            nxt = last + debounce_sec
            write_jsonl(
                memo_path,
                {"ts": now_ts, "type": "suppressed", "uid": uid, "rule": "combo", "next": nxt},
            )
            suppressed_now.add(key)
            # Render the row with a muted hint
            rows.append(
                {
                    "uid": uid,
                    "sleeve": "theta",
                    "kind": c.kind,
                    "R": round(c.max_loss, 2),
                    "stop": "-",
                    "target": "-",
                    "mark": round(c.credit, 2),
                    "alert": (reason or "") + " (debounced)",
                }
            )
            continue

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
        _last_alert_ts[key] = now_ts
    if mark_backfills:
        for sym in mark_backfills:
            write_jsonl(
                memo_path,
                {
                    "ts": now_ts,
                    "type": "info",
                    "uid": f"STK-{sym}",
                    "rule": "mark-backfill",
                    "message": f"mark from yf for {sym}",
                },
            )

    for o in orphans:
        uid = f"{o['symbol']}-{o['expiry']}-orphan-{o['side']}"
        key = (uid, "orphan")
        until = _snooze_until.get(key, 0)
        if until and now_ts < until:
            write_jsonl(
                memo_path,
                {"ts": now_ts, "type": "snoozed", "uid": uid, "rule": "orphan", "next": until},
            )
            rows.append(
                {
                    "uid": uid,
                    "sleeve": "theta",
                    "kind": "orphan",
                    "R": 0,
                    "stop": "-",
                    "target": "-",
                    "mark": None,
                    "alert": (o.get("reason", "") + " [SNOOZED]"),
                }
            )
        else:
            last = _last_alert_ts.get(key, 0)
            if last and (now_ts - last) < debounce_sec:
                nxt = last + debounce_sec
                write_jsonl(
                    memo_path, {"ts": now_ts, "type": "suppressed", "uid": uid, "rule": "orphan", "next": nxt}
                )
                rows.append(
                    {
                        "uid": uid,
                        "sleeve": "theta",
                        "kind": "orphan",
                        "R": 0,
                        "stop": "-",
                        "target": "-",
                        "mark": None,
                        "alert": (o.get("reason", "") + " (debounced)"),
                    }
                )
            else:
                alerts.append(
                    Alert(uid=uid, rule="orphan", severity="warn", message=o.get("reason", "orphan-risk"))
                )
                rows.append(
                    {
                        "uid": uid,
                        "sleeve": "theta",
                        "kind": "orphan",
                        "R": 0,
                        "stop": "-",
                        "target": "-",
                        "mark": None,
                        "alert": o.get("reason", ""),
                    }
                )
                _last_alert_ts[key] = now_ts

    # Budgets footer
    fees_wtd = float(cfg.get("theta_fees_wtd", 0.0))
    hedge_mtd = float(cfg.get("hedge_cost_mtd", 0.0))
    thresholds = cfg.get("budgets") if isinstance(cfg.get("budgets"), dict) else {}
    budgets_dto = budget_rules.footer_dto(nav, fees_wtd, hedge_mtd, thresholds)

    # Write memos
    ts = now_ts
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
        "alerts": [
            {"uid": a.uid, "rule": a.rule, "severity": a.severity, "message": a.message, "data": a.data}
            for a in alerts
        ],
        "rows": rows,
    }


def compute_snapshot(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Lightweight helper returning risk snapshot context without memo side-effects."""
    cfg = cfg or {}
    nav = float(cfg.get("nav", 100_000.0))
    positions = _load_positions(cfg)
    snapshot, band_key, breaches, breakers, breaker_state = _risk_context(positions, cfg, nav)
    return {
        "snapshot": snapshot,
        "band": band_key,
        "breaches": breaches,
        "breakers": breakers,
        "breaker_state": breaker_state,
    }
