# SPDX-License-Identifier: MIT

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from positions_engine.core.marks import MarkSettings, select_equity_mark
from positions_engine.core.models import Quote, TradingSession
from positions_engine.service.state import PositionsState


def test_rth_prefers_mid_over_last() -> None:
    now = datetime.now(tz=UTC)
    quote = Quote(
        symbol="AAPL",
        bid=100,
        bid_ts=now - timedelta(seconds=5),
        ask=102,
        ask_ts=now - timedelta(seconds=5),
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
        bid_ts=now - timedelta(seconds=2),
        ask=202,
        ask_ts=now - timedelta(seconds=1),
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
        last_ts=now,
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
        bid_ts=now - timedelta(seconds=3),
        ask=904,
        ask_ts=now - timedelta(seconds=2),
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
        last_ts=now - timedelta(seconds=5),
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
            last_ts=now - timedelta(seconds=seconds_ago),
            previous_close=49,
            session=session,
            updated_at=now - timedelta(seconds=seconds_ago),
        )
        result = select_equity_mark(quote=quote, now=now)
        assert result.threshold == expected_threshold
        assert result.is_stale is should_be_stale


def test_mid_mark_uses_bid_ask_timestamps_for_staleness() -> None:
    now = datetime.now(tz=UTC)
    quote = Quote(
        symbol="MSFT",
        bid=Decimal("100"),
        bid_ts=now - timedelta(seconds=25),
        ask=Decimal("101"),
        ask_ts=now - timedelta(seconds=10),
        session=TradingSession.RTH,
    )

    result = select_equity_mark(quote=quote, now=now)

    assert result.source == "MID"
    assert result.stale_seconds == 10


def test_last_mark_uses_last_timestamp_for_staleness() -> None:
    now = datetime.now(tz=UTC)
    quote = Quote(
        symbol="META",
        last=Decimal("150"),
        last_ts=now - timedelta(seconds=45),
        previous_close=Decimal("148"),
        session=TradingSession.RTH,
    )

    result = select_equity_mark(quote=quote, now=now)

    assert result.source == "LAST"
    assert result.stale_seconds == 45


def test_mid_mark_without_timestamps_falls_back_to_conservative_age() -> None:
    now = datetime.now(tz=UTC)
    quote = Quote(
        symbol="AMD",
        bid=Decimal("95"),
        ask=Decimal("96"),
        session=TradingSession.RTH,
    )

    result = select_equity_mark(quote=quote, now=now)

    assert result.source == "MID"
    assert result.stale_seconds >= 23 * 60 * 60


def test_prev_mark_uses_previous_close_ts_for_staleness() -> None:
    now = datetime(2024, 1, 3, 14, 30, tzinfo=UTC)
    prev_close_ts = datetime(2024, 1, 2, 21, 0, tzinfo=UTC)
    quote = Quote(
        symbol="AAPL",
        bid=None,
        ask=None,
        last=None,
        previous_close=Decimal("195.10"),
        previous_close_ts=prev_close_ts,
        session=TradingSession.CLOSED,
        updated_at=now,
    )

    result = select_equity_mark(quote=quote, now=now)

    assert result.source == "PREV"
    assert result.mark == quote.previous_close
    assert result.stale_seconds == int((now - prev_close_ts).total_seconds())


def test_prev_mark_without_timestamp_falls_back_to_default_staleness() -> None:
    now = datetime(2024, 1, 4, 9, 30, tzinfo=UTC)
    quote = Quote(
        symbol="MSFT",
        bid=None,
        ask=None,
        last=None,
        previous_close=Decimal("380.00"),
        session=TradingSession.CLOSED,
        updated_at=now,
    )

    result = select_equity_mark(quote=quote, now=now)

    assert result.source == "PREV"
    assert result.mark == quote.previous_close
    assert result.stale_seconds == 24 * 60 * 60


def test_positions_view_option_leg_mid_staleness() -> None:
    state = PositionsState()
    now = datetime(2024, 1, 5, 15, 0, tzinfo=UTC)
    bid_ts = now - timedelta(seconds=45)
    ask_ts = now - timedelta(seconds=18)
    positions_view = {
        "single_stocks": [],
        "option_combos": [],
        "single_options": [
            {
                "symbol": "XYZ 20240105 C100",
                "qty": 1.0,
                "avg_cost": 2.5,
                "mark": 2.6,
                "mark_source": "mid",
                "stale_seconds": 0,
                "bidQuoteTimestamp": bid_ts.isoformat(),
                "ask_timestamp": ask_ts.isoformat(),
            }
        ],
    }
    state.refresh(positions_view=positions_view)

    payload = state.positions_view_payload(now)
    option = payload["single_options"][0]

    assert option["mark_source"] == "MID"
    assert option["bid_ts"] == bid_ts.isoformat()
    assert option["ask_ts"] == ask_ts.isoformat()
    assert option["bidQuoteTimestamp"] == bid_ts.isoformat()
    assert option["ask_timestamp"] == ask_ts.isoformat()
    assert option["stale_seconds"] == int((now - ask_ts).total_seconds())
    assert option["stale_seconds"] > 0
    assert option["stale_s"] == option["stale_seconds"]


def test_positions_view_option_leg_last_staleness() -> None:
    state = PositionsState()
    now = datetime(2024, 1, 5, 15, 0, tzinfo=UTC)
    last_ts = now - timedelta(seconds=75)
    positions_view = {
        "single_stocks": [],
        "option_combos": [],
        "single_options": [
            {
                "symbol": "XYZ 20240105 P90",
                "qty": -1.0,
                "avg_cost": 1.1,
                "mark": 1.0,
                "mark_source": "LAST",
                "stale_seconds": 0,
                "lastTradeTimestamp": last_ts.isoformat(),
            }
        ],
    }
    state.refresh(positions_view=positions_view)

    payload = state.positions_view_payload(now)
    option = payload["single_options"][0]

    assert option["mark_source"] == "LAST"
    assert option["last_ts"] == last_ts.isoformat()
    assert option["lastTradeTimestamp"] == last_ts.isoformat()
    assert option["stale_seconds"] == int((now - last_ts).total_seconds())
    assert option["stale_seconds"] > 0
    assert option["stale_s"] == option["stale_seconds"]


def test_positions_view_option_leg_prev_from_last_close() -> None:
    state = PositionsState()
    prev_close_ts = datetime(2024, 1, 4, 21, 0, tzinfo=UTC)
    now = prev_close_ts + timedelta(hours=6)
    positions_view = {
        "single_stocks": [],
        "option_combos": [],
        "single_options": [
            {
                "symbol": "XYZ 20240105 C95",
                "qty": 2.0,
                "avg_cost": 3.2,
                "mark": 3.3,
                "mark_source": "LAST_CLOSE",
                "stale_seconds": 0,
                "previous_close_ts": prev_close_ts.isoformat(),
            }
        ],
    }
    state.refresh(positions_view=positions_view)

    payload = state.positions_view_payload(now)
    option = payload["single_options"][0]

    assert option["mark_source"] == "PREV"
    assert option["price_source"] == "prev"
    assert option["stale_seconds"] == int((now - prev_close_ts).total_seconds())
    assert option["stale_seconds"] > 0
    assert option["stale_s"] == option["stale_seconds"]
