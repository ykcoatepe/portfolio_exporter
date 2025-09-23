from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from positions_engine.core.marks import MarkSettings, select_equity_mark
from positions_engine.core.models import Quote, TradingSession


def _make_quote(
    *,
    bid: str,
    ask: str,
    session: TradingSession,
    updated_at: datetime | None = None,
) -> Quote:
    return Quote(
        symbol="SPY",
        bid=Decimal(bid),
        ask=Decimal(ask),
        session=session,
        updated_at=updated_at,
    )


def test_mid_mark_staleness_uses_updated_at_when_bid_ask_timestamps_missing() -> None:
    now = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
    quote = _make_quote(bid="100", ask="101", session=TradingSession.RTH, updated_at=now)

    result = select_equity_mark(quote, now=now, settings=MarkSettings())

    assert result.source == "MID"
    assert result.stale_seconds == 0
    assert result.is_stale is False


def test_mid_mark_staleness_falls_back_to_prev_when_no_timestamps() -> None:
    now = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
    quote = _make_quote(bid="100", ask="101", session=TradingSession.RTH)

    result = select_equity_mark(quote, now=now, settings=MarkSettings())

    assert result.source == "MID"
    assert result.stale_seconds == 24 * 60 * 60


def test_mid_mark_prefers_bid_ask_timestamps_over_updated_at() -> None:
    now = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
    quote = _make_quote(
        bid="100",
        ask="101",
        session=TradingSession.RTH,
        updated_at=now,
    )

    stale_ts = now - timedelta(seconds=45)
    quote = quote.model_copy(update={"bid_ts": stale_ts, "ask_ts": stale_ts})

    result = select_equity_mark(quote, now=now, settings=MarkSettings())

    assert result.source == "MID"
    assert result.stale_seconds == 45
    assert result.is_stale is True


def test_last_mark_staleness_uses_updated_at_when_timestamp_missing() -> None:
    now = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
    quote = Quote(
        symbol="SPY",
        last=Decimal("101"),
        session=TradingSession.RTH,
        updated_at=now,
    )

    result = select_equity_mark(quote, now=now, settings=MarkSettings())

    assert result.source == "LAST"
    assert result.stale_seconds == 0
    assert result.is_stale is False


def test_prev_mark_staleness_uses_updated_at_when_timestamp_missing() -> None:
    now = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
    quote = Quote(
        symbol="SPY",
        previous_close=Decimal("100"),
        session=TradingSession.RTH,
        updated_at=now,
    )

    result = select_equity_mark(quote, now=now, settings=MarkSettings())

    assert result.source == "PREV"
    assert result.stale_seconds == 0
    assert result.is_stale is False
