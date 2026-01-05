from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from psd.sentinel.msb_metrics import LIVEBAR_ROWS

_TRT = ZoneInfo("Europe/Istanbul")
_COLUMNS = [
    "Hedge",
    "Cost % NAV",
    "Status",
    "Expiry",
    "Trigger",
    "TriggerTimeTRT",
    "Notes",
]


def _ensure_trt(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_TRT)
    return dt.astimezone(_TRT)


def _add_business_days(start: datetime, days: int) -> datetime:
    target = start
    added = 0
    while added < days:
        target += timedelta(days=1)
        if target.weekday() < 5:
            added += 1
    return target


def _append_note(existing: str, extra: str) -> str:
    extra_clean = extra.strip()
    if not extra_clean:
        return existing.strip()
    if not existing.strip():
        return extra_clean
    if extra_clean in existing:
        return existing.strip()
    return f"{existing.strip()}; {extra_clean}"


_RULE_DEFAULTS: dict[str, dict[str, Any]] = {
    "A": {
        "hedge": "VIX 25/35 call spread (2–4w)",
        "cost": "0.10–0.35",
        "status": "STAGED",
        "expiry": lambda base: (base + timedelta(days=21)).date().isoformat(),
        "trigger": "RULE_A_VIX_BACKWARDATION",
    },
    "B": {
        "hedge": "SPX put spread (2–4w)",
        "cost": "0.15–0.40",
        "status": "STAGED",
        "expiry": lambda base: (base + timedelta(days=21)).date().isoformat(),
        "trigger": "RULE_B_HY_SHOCK",
    },
    "C": {
        "hedge": "Reduce beta (−20–40%)",
        "cost": "—",
        "status": "LIVE",
        "expiry": lambda base: _add_business_days(base, 5).date().isoformat(),
        "trigger": "RULE_C_MSB_60x3D",
    },
}


def update_live_status_bar(
    trigger: str,
    when_trt: datetime,
    msb: int,
    color: str,
    notes: str = "",
) -> Path:
    """Append or update the live status bar hedges CSV."""
    rule_key = trigger.strip().upper()
    if rule_key not in _RULE_DEFAULTS:
        raise ValueError(f"Unsupported MSB trigger '{trigger}'")

    defaults = _RULE_DEFAULTS[rule_key]
    ts_trt = _ensure_trt(when_trt)

    path = Path("data") / "live_status_bar.csv"
    path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, str]] = []
    if path.exists():
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                rows.append({col: row.get(col, "").strip() for col in _COLUMNS})

    trigger_name = defaults["trigger"]
    live_duplicate = None
    for row in rows:
        if row.get("Trigger") == trigger_name and row.get("Status") == "LIVE":
            live_duplicate = row
            break

    extra_note = notes.strip()

    if live_duplicate is not None:
        duplicate_note = "already hedged; maintain size"
        live_duplicate["Notes"] = _append_note(
            live_duplicate.get("Notes", ""), duplicate_note
        )
        if extra_note:
            live_duplicate["Notes"] = _append_note(live_duplicate["Notes"], extra_note)
    else:
        expiry_value = defaults["expiry"](ts_trt)
        base_note = extra_note
        if rule_key == "C" and extra_note:
            base_note = extra_note

        row = {
            "Hedge": defaults["hedge"],
            "Cost % NAV": defaults["cost"],
            "Status": defaults["status"],
            "Expiry": expiry_value,
            "Trigger": trigger_name,
            "TriggerTimeTRT": ts_trt.isoformat(timespec="seconds"),
            "Notes": base_note,
        }
        rows.append(row)
        LIVEBAR_ROWS.inc()

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    return path


__all__ = ["update_live_status_bar"]
