# SPDX-License-Identifier: MIT

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from positions_engine.core.marks import MarkSettings, select_equity_mark
from positions_engine.core.models import Quote, TradingSession


def test_rth_prefers_mid_over_last() -> None:
    now = datetime.now(tz=UTC)
    quote = Quote(
        symbol="AAPL",
        bid=100,
        ask=102,
        last=105,
        previous_close=98,
        session=TradingSession.RTH,
        updated_at=now - timedelta(seconds=5),
    )
    result = select_equity_mark(quote=quote, now=now, settings=MarkSettings())
    assert result.mark == quote.mid
    assert result.source == "MID"
    assert result.is_stale is False


def test_eth_fallbacks_mid_last_prev() -> None:
    now = datetime.now(tz=UTC)
    # MID available wins
    with_mid = Quote(
        symbol="TSLA",
        bid=200,
        ask=202,
        last=205,
        previous_close=198,
        session=TradingSession.ETH,
        updated_at=now,
    )
    result_mid = select_equity_mark(quote=with_mid, now=now)
    assert result_mid.source == "MID"

    # MID missing -> use extended/last
    fallback_last = Quote(
        symbol="TSLA",
        last=None,
        extended_last=241,
        previous_close=238,
        session=TradingSession.ETH,
        updated_at=now,
    )
    result_last = select_equity_mark(quote=fallback_last, now=now)
    assert result_last.mark == fallback_last.extended_last
    assert result_last.source == "LAST"

    # No MID or LAST → PREV
    fallback_prev = Quote(
        symbol="TSLA",
        last=None,
        extended_last=None,
        previous_close=238,
        session=TradingSession.ETH,
        updated_at=now,
    )
    result_prev = select_equity_mark(quote=fallback_prev, now=now)
    assert result_prev.mark == fallback_prev.previous_close
    assert result_prev.source == "PREV"


def test_closed_fallbacks_mid_last_prev() -> None:
    now = datetime.now(tz=UTC)
    with_mid = Quote(
        symbol="NVDA",
        bid=900,
        ask=904,
        last=902,
        previous_close=880,
        session=TradingSession.CLOSED,
        updated_at=now,
    )
    result_mid = select_equity_mark(quote=with_mid, now=now)
    assert result_mid.source == "MID"

    fallback_last = Quote(
        symbol="NVDA",
        last=901,
        previous_close=880,
        session=TradingSession.CLOSED,
        updated_at=now,
    )
    result_last = select_equity_mark(quote=fallback_last, now=now)
    assert result_last.source == "LAST"

    fallback_prev = Quote(
        symbol="NVDA",
        last=None,
        previous_close=880,
        session=TradingSession.CLOSED,
        updated_at=now,
    )
    result_prev = select_equity_mark(quote=fallback_prev, now=now)
    assert result_prev.source == "PREV"


def test_stale_thresholds_colorization() -> None:
    now = datetime.now(tz=UTC)
    cases = [
        (TradingSession.RTH, 29, False, 30),
        (TradingSession.RTH, 31, True, 30),
        (TradingSession.ETH, 75, False, 90),
        (TradingSession.ETH, 95, True, 90),
        (TradingSession.CLOSED, 3500, False, 3600),
        (TradingSession.CLOSED, 3610, True, 3600),
    ]
    for session, seconds_ago, should_be_stale, expected_threshold in cases:
        quote = Quote(
            symbol="ABC",
            last=50,
            previous_close=49,
            session=session,
            updated_at=now - timedelta(seconds=seconds_ago),
        )
        result = select_equity_mark(quote=quote, now=now)
        assert result.threshold == expected_threshold
        assert result.is_stale is should_be_stale
