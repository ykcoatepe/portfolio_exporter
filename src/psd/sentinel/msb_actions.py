from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI

from psd.core import store
from psd.sentinel.engine import evaluate_msb_triggers
from psd.sentinel.msb_metrics import MSB_ALERTS
from psd.ui.livebar import update_live_status_bar
from psd.web.sse import SseManager

_TRT = ZoneInfo("Europe/Istanbul")
_LOG = logging.getLogger("psd.sentinel.msb")


def _log_alert(alert: Any) -> None:
    payload = getattr(alert, "data", {}) or {}
    try:
        encoded = json.dumps(
            {"event": "msb.alert", "rule": getattr(alert, "rule", ""), "data": payload},
            separators=(",", ":"),
            sort_keys=True,
        )
    except Exception:
        encoded = f"msb.alert {getattr(alert, 'rule', '')}"
    _LOG.info(encoded)


def _ensure_context(context: dict[str, Any]) -> dict[str, Any]:
    ctx = dict(context)
    msb_row = ctx.get("msb_row")
    if not msb_row:
        msb_row = store.read_msb_current()
        if not msb_row:
            return ctx
        ctx["msb_row"] = msb_row
    if "today" not in ctx:
        raw_date = msb_row.get("date")
        if isinstance(raw_date, str):
            try:
                ctx["today"] = date.fromisoformat(raw_date)
            except ValueError:
                ctx["today"] = None
    need_hy = ctx.get("hy_d1_bps") is None or ctx.get("hy_d5_bps") is None
    need_streak = ctx.get("streak_ge_60") is None
    if need_hy or need_streak:
        history = store.read_msb_history(days=6)
        if history:
            sorted_history = sorted(history, key=lambda row: row.get("date", ""))
            latest = sorted_history[-1]
            prev = sorted_history[-2] if len(sorted_history) >= 2 else None
            prev5 = sorted_history[-6] if len(sorted_history) >= 6 else None
            if need_hy:
                hy_latest = float(latest.get("hy", 0.0) or 0.0)
                if prev is not None:
                    hy_prev = float(prev.get("hy", 0.0) or 0.0)
                    ctx["hy_d1_bps"] = (hy_latest - hy_prev) * 100.0
                if prev5 is not None:
                    hy_prev5 = float(prev5.get("hy", 0.0) or 0.0)
                    ctx["hy_d5_bps"] = (hy_latest - hy_prev5) * 100.0
            if need_streak:
                streak = 0
                for row in reversed(sorted_history):
                    try:
                        value = float(row.get("msb", 0) or 0)
                    except (TypeError, ValueError):
                        value = 0.0
                    if value >= 60:
                        streak += 1
                    else:
                        break
                ctx["streak_ge_60"] = streak
    if "cooldown_started_today" not in ctx:
        triggers = msb_row.get("triggers") or []
        ctx["cooldown_started_today"] = "C" in {str(flag).upper() for flag in triggers}
    if "cooldown_until" not in ctx:
        cooldown_raw = msb_row.get("cooldown_until")
        if isinstance(cooldown_raw, str):
            try:
                ctx["cooldown_until"] = date.fromisoformat(cooldown_raw)
            except ValueError:
                ctx["cooldown_until"] = None
        else:
            ctx["cooldown_until"] = None
    return ctx


def _broadcast_alerts(app: FastAPI, alerts: Iterable[Any]) -> None:
    manager = getattr(app.state, "sse", None)
    if not isinstance(manager, SseManager):
        return
    for alert in alerts:
        data = getattr(alert, "data", {}) or {}
        payload = {
            "rule": getattr(alert, "rule", ""),
            "msb": data.get("msb"),
            "color": data.get("color"),
            "hy_score": data.get("hy_score"),
            "vix_score": data.get("vix_score"),
            "term_ratio": data.get("term_ratio"),
            "vx_ratio": data.get("vx_ratio"),
            "why": data.get("why"),
            "actions": data.get("actions") or [],
        }
        cooldown_until = data.get("cooldown_until")
        if cooldown_until:
            payload["cooldown_until"] = cooldown_until
        manager.broadcast("sentinel.alert", payload)


def _update_livebar(alerts: Iterable[Any], context: dict[str, Any]) -> None:
    when_trt = datetime.now(tz=_TRT)
    msb_row = context.get("msb_row") or {}
    msb_value = int(msb_row.get("msb", 0) or 0)
    color = str(msb_row.get("color") or "")
    for alert in alerts:
        rule = getattr(alert, "rule", "")
        if not rule:
            continue
        notes = ""
        cooldown = getattr(alert, "data", {}).get("cooldown_until")
        if rule == "C" and cooldown:
            notes = f"cooldown until {cooldown}"
        update_live_status_bar(rule, when_trt, msb_value, color, notes=notes)


def evaluate_msb_triggers_and_update_livebar(
    app: FastAPI,
    context: dict[str, Any] | None = None,
) -> list[Any]:
    """Evaluate MSB triggers, emit SSE alerts, and update the live status bar."""
    ctx = _ensure_context(context or {})
    msb_row = ctx.get("msb_row")
    if not msb_row:
        return []

    alerts = evaluate_msb_triggers(msb_row, ctx)
    if not alerts:
        return []

    _broadcast_alerts(app, alerts)
    _update_livebar(alerts, ctx)

    for alert in alerts:
        rule = getattr(alert, "rule", "")
        if rule:
            MSB_ALERTS.labels(rule=rule).inc()
        _log_alert(alert)
    return alerts


__all__ = ["evaluate_msb_triggers_and_update_livebar"]
