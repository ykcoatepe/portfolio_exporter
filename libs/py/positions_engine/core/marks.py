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
    stale_seconds = _compute_staleness(quote, now)
    return MarkResult(mark=mark, source=source, stale_seconds=stale_seconds, threshold=threshold)


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


def _first_present(candidates: list[tuple[Decimal | None, str]]) -> tuple[Decimal | None, str]:
    for value, label in candidates:
        if value is not None:
            return value, label
    return None, _MARK_SOURCE_MISSING


def _compute_staleness(quote: Quote | None, now: datetime) -> int | None:
    if quote is None or quote.updated_at is None:
        return None
    quote_ts = quote.updated_at
    if quote_ts.tzinfo is None:
        quote_ts = quote_ts.replace(tzinfo=UTC)
    delta = now - quote_ts
    total = int(max(delta.total_seconds(), 0))
    return total
