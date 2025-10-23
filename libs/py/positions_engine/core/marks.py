# SPDX-License-Identifier: MIT

"""Deterministic mark selection helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from .models import Quote, TradingSession


@dataclass(frozen=True)
class MarkSettings:
    """Configuration for mark selection and staleness thresholds."""

    session_thresholds: Mapping[TradingSession, int] = field(
        default_factory=lambda: {
            TradingSession.RTH: 30,
            TradingSession.ETH: 90,
            TradingSession.CLOSED: 3600,
        }
    )

    def threshold_for(self, session: TradingSession) -> int:
        return int(self.session_thresholds.get(session, 300))


@dataclass(frozen=True)
class MarkResult:
    """Result payload for mark computations."""

    mark: Decimal | None
    source: str
    stale_seconds: int | None
    threshold: int

    @property
    def is_stale(self) -> bool:
        return (self.stale_seconds or 0) > self.threshold


def select_equity_mark(
    quote: Quote | None,
    now: datetime | None = None,
    settings: MarkSettings | None = None,
) -> MarkResult:
    """Return the best mark for an equity quote given the current session.

    Selection order is session aligned with the downstream contract:
    - RTH / ETH: MID → LAST → PREV
    - CLOSED   : MID → LAST → PREV
    """

    if settings is None:
        settings = MarkSettings()
    session = TradingSession.CLOSED
    if quote is not None:
        session = quote.session
    threshold = settings.threshold_for(session)

    if now is None:
        now = datetime.now(tz=UTC)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    mark: Decimal | None = None
    source = _MARK_SOURCE_MISSING

    if quote is not None:
        mark, source = _pick_mark(quote)
    stale_seconds = _compute_staleness(quote, now, source)
    return MarkResult(
        mark=mark, source=source, stale_seconds=stale_seconds, threshold=threshold
    )


_MARK_SOURCE_MID = "MID"
_MARK_SOURCE_LAST = "LAST"
_MARK_SOURCE_PREV = "PREV"
_MARK_SOURCE_MISSING = "MISSING"


def _pick_mark(quote: Quote) -> tuple[Decimal | None, str]:
    last_value = quote.last
    if quote.session == TradingSession.ETH and quote.extended_last is not None:
        last_value = quote.extended_last
    candidates = [
        (quote.mid, _MARK_SOURCE_MID),
        (last_value, _MARK_SOURCE_LAST),
        (quote.previous_close, _MARK_SOURCE_PREV),
    ]
    return _first_present(candidates)


def _first_present(
    candidates: list[tuple[Decimal | None, str]],
) -> tuple[Decimal | None, str]:
    for value, label in candidates:
        if value is not None:
            return value, label
    return None, _MARK_SOURCE_MISSING


_PREV_STALE_FALLBACK_SECONDS = 24 * 60 * 60


def _normalize_timestamp(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _latest_timestamp(*timestamps: datetime | None) -> datetime | None:
    normalized: list[datetime] = []
    for ts in timestamps:
        normalized_ts = _normalize_timestamp(ts)
        if normalized_ts is not None:
            normalized.append(normalized_ts)
    if not normalized:
        return None
    return max(normalized)


def _seconds_between(now: datetime, then: datetime) -> int:
    delta = now - then
    return int(max(delta.total_seconds(), 0))


def _compute_staleness(quote: Quote | None, now: datetime, source: str) -> int | None:
    if quote is None:
        return None

    source_upper = (source or "").upper()
    if source_upper == _MARK_SOURCE_PREV:
        timestamp = _normalize_timestamp(getattr(quote, "previous_close_ts", None))
        if timestamp is not None:
            return _seconds_between(now, timestamp)
        fallback_ts = _normalize_timestamp(getattr(quote, "updated_at", None))
        if fallback_ts is not None:
            return _seconds_between(now, fallback_ts)
        return _PREV_STALE_FALLBACK_SECONDS

    if source_upper == _MARK_SOURCE_MID:
        latest_ts = _latest_timestamp(
            getattr(quote, "bid_ts", None),
            getattr(quote, "ask_ts", None),
        )
        if latest_ts is not None:
            return _seconds_between(now, latest_ts)

        fallback_ts = _normalize_timestamp(getattr(quote, "updated_at", None))
        if fallback_ts is not None:
            return _seconds_between(now, fallback_ts)
        return _PREV_STALE_FALLBACK_SECONDS

    if source_upper == _MARK_SOURCE_LAST:
        timestamp = _normalize_timestamp(getattr(quote, "last_ts", None))
        if timestamp is not None:
            return _seconds_between(now, timestamp)
        fallback_ts = _normalize_timestamp(getattr(quote, "updated_at", None))
        if fallback_ts is not None:
            return _seconds_between(now, fallback_ts)
        return _PREV_STALE_FALLBACK_SECONDS

    quote_ts = _normalize_timestamp(quote.updated_at)
    if quote_ts is None:
        return None
    return _seconds_between(now, quote_ts)
