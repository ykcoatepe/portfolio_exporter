# SPDX-License-Identifier: MIT

"""Market session detection helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

VALID_STATES = {"RTH", "ETH", "CLOSED"}


@dataclass(frozen=True)
class SessionInfo:
    """Describes the currently active trading session."""

    exchange: str
    tz: str
    state: str
    as_of: str
    rth_open: str | None = None
    rth_close: str | None = None
    source: str = "fallback"
    note: str | None = None


def _ensure_ny(now: datetime, tz: ZoneInfo) -> datetime:
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC).astimezone(tz)
    return now.astimezone(tz)


def _calendar_session(now: datetime, tz: ZoneInfo) -> SessionInfo | None:
    """Attempt to classify session using optional calendar libraries."""

    try:
        import exchange_calendars as xc  # type: ignore
    except Exception:  # pragma: no cover - optional dependency
        xc = None

    if xc is not None:
        try:
            nyse = xc.get_calendar("XNYS")
            sched = nyse.schedule(now.date(), now.date())
        except Exception:  # pragma: no cover - defensive, optional dep failures
            sched = None
        if sched is not None and not sched.empty:
            rth_open = sched.iloc[0]["market_open"].to_pydatetime().astimezone(tz)
            rth_close = sched.iloc[0]["market_close"].to_pydatetime().astimezone(tz)
            state = _classify(now, rth_open, rth_close)
            return SessionInfo(
                "XNYS",
                tz.key,
                state,
                now.isoformat(),
                rth_open=rth_open.isoformat(),
                rth_close=rth_close.isoformat(),
                source="calendar",
            )

    try:
        import pandas_market_calendars as pmc  # type: ignore
    except Exception:  # pragma: no cover - optional dependency
        pmc = None

    if pmc is not None:
        try:
            nyse = pmc.get_calendar("XNYS")
            sched = nyse.schedule(start_date=now.date(), end_date=now.date())
        except Exception:  # pragma: no cover - defensive
            sched = None
        if sched is not None and not sched.empty:
            rth_open = sched.iloc[0]["market_open"].to_pydatetime().astimezone(tz)
            rth_close = sched.iloc[0]["market_close"].to_pydatetime().astimezone(tz)
            state = _classify(now, rth_open, rth_close)
            return SessionInfo(
                "XNYS",
                tz.key,
                state,
                now.isoformat(),
                rth_open=rth_open.isoformat(),
                rth_close=rth_close.isoformat(),
                source="calendar",
            )

    return None


def _classify(now: datetime, rth_open: datetime, rth_close: datetime) -> str:
    pre_market_window = (time(4, 0), rth_open.time().replace(tzinfo=None))
    post_market_window = (rth_close.time().replace(tzinfo=None), time(20, 0))

    current_time = now.time().replace(tzinfo=None)
    if rth_open <= now < rth_close:
        return "RTH"
    if pre_market_window[0] <= current_time < pre_market_window[1]:
        return "ETH"
    if post_market_window[0] <= current_time < post_market_window[1]:
        return "ETH"
    return "CLOSED"


def _fallback_session(now: datetime) -> SessionInfo:
    rth_open = time(9, 30)
    rth_close = time(16, 0)
    eth_pre_open = time(4, 0)
    eth_post_close = time(20, 0)
    is_weekday = now.weekday() < 5

    current_time = now.time().replace(tzinfo=None)
    if is_weekday and rth_open <= current_time < rth_close:
        state = "RTH"
    elif is_weekday and (
        eth_pre_open <= current_time < rth_open
        or rth_close <= current_time < eth_post_close
    ):
        state = "ETH"
    else:
        state = "CLOSED"

    return SessionInfo(
        "XNYS",
        now.tzinfo.key if hasattr(now.tzinfo, "key") else "America/New_York",
        state,
        now.isoformat(),
        source="fallback",
    )


def detect_session(now: datetime | None = None) -> SessionInfo:
    """Detect the current trading session.

    - Prefer an exchange calendar when available.
    - Fall back to static time windows when not.
    - Allow FORCE_SESSION_STATE overrides for development.
    """

    override = os.getenv("FORCE_SESSION_STATE")
    ny_tz = ZoneInfo("America/New_York")
    current = _ensure_ny(now or datetime.now(UTC), ny_tz)

    if override:
        state = override.strip().upper()
        note = None
        if state not in VALID_STATES:
            note = f"invalid override: {override}"
            state = "CLOSED"
        return SessionInfo(
            "XNYS",
            ny_tz.key,
            state,
            current.isoformat(),
            source="override",
            note=note,
        )

    calendar_session = _calendar_session(current, ny_tz)
    if calendar_session is not None:
        return calendar_session

    return _fallback_session(current)
