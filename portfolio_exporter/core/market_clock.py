from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, time
from typing import Optional
from zoneinfo import ZoneInfo

TZ_NY = ZoneInfo("America/New_York")
TZ_TR = ZoneInfo("Europe/Istanbul")


@dataclass
class RTHWindowTR:
    open_tr: datetime
    close_tr: datetime
    # convenience “afternoon re-arm anchor” as an ET time converted to TR
    afternoon_rearm_tr: Optional[datetime] = None
    # time after which new signals are not started (TR)
    no_new_signals_after_tr: Optional[datetime] = None


@dataclass
class SessionWindowTR:
    start_tr: datetime
    end_tr: datetime


def _combine(d: date, hh: int, mm: int, tz: ZoneInfo) -> datetime:
    return datetime(d.year, d.month, d.day, hh, mm, tzinfo=tz)


def rth_window_tr(
    today_tr: Optional[date] = None,
    et_open: time = time(9, 30),
    et_close: time = time(16, 0),
    et_afternoon_rearm: Optional[time] = time(13, 30),
    et_no_new_after: Optional[time] = time(15, 30),
) -> RTHWindowTR:
    """
    Returns the RTH open/close and optional anchors expressed in Europe/Istanbul for
    'today' in TR. The ET anchors are NYSE/Nasdaq RTH (NY time) and are converted
    with zoneinfo (DST-aware).
    """
    # Find 'today' in NY, not TR, to anchor ET day correctly
    now_ny = datetime.now(TZ_NY)
    ny_day = now_ny.date()

    open_tr = _combine(ny_day, et_open.hour, et_open.minute, TZ_NY).astimezone(TZ_TR)
    close_tr = _combine(ny_day, et_close.hour, et_close.minute, TZ_NY).astimezone(TZ_TR)

    aft_tr = (
        _combine(ny_day, et_afternoon_rearm.hour, et_afternoon_rearm.minute, TZ_NY).astimezone(TZ_TR)
        if et_afternoon_rearm
        else None
    )
    cutoff_tr = (
        _combine(ny_day, et_no_new_after.hour, et_no_new_after.minute, TZ_NY).astimezone(TZ_TR)
        if et_no_new_after
        else None
    )

    return RTHWindowTR(
        open_tr=open_tr,
        close_tr=close_tr,
        afternoon_rearm_tr=aft_tr,
        no_new_signals_after_tr=cutoff_tr,
    )


def premarket_window_tr(
    et_start: time = time(4, 0),
    et_end: time = time(9, 30),
) -> SessionWindowTR:
    """Return TR-local pre-market window (default 04:00-09:30 ET)."""
    now_ny = datetime.now(TZ_NY)
    ny_day = now_ny.date()
    start_tr = _combine(ny_day, et_start.hour, et_start.minute, TZ_NY).astimezone(TZ_TR)
    end_tr = _combine(ny_day, et_end.hour, et_end.minute, TZ_NY).astimezone(TZ_TR)
    return SessionWindowTR(start_tr=start_tr, end_tr=end_tr)


def is_after(dt_tr: datetime, now_tr: Optional[datetime] = None) -> bool:
    now_tr = now_tr or datetime.now(TZ_TR)
    return now_tr >= dt_tr


def pretty_tr(dt_tr: Optional[datetime]) -> str:
    return dt_tr.astimezone(TZ_TR).strftime("%Y-%m-%d %H:%M") if dt_tr else "-"

