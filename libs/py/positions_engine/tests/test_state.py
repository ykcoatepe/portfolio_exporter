# SPDX-License-Identifier: MIT

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from positions_engine.core.models import (
    Instrument,
    InstrumentType,
    Position,
    Quote,
    TradingSession,
)
from positions_engine.service.state import PositionsState


def test_equities_payload_emits_pnl_and_percentages() -> None:
    state = PositionsState()
    instrument = Instrument(
        symbol="AAPL", instrument_type=InstrumentType.EQUITY, multiplier=Decimal("1")
    )
    position = Position(
        instrument=instrument, quantity=Decimal("200"), avg_cost=Decimal("10")
    )
    now = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
    quote = Quote(
        symbol="AAPL",
        bid=Decimal("11"),
        bid_ts=now - timedelta(seconds=12),
        ask=Decimal("12"),
        ask_ts=now - timedelta(seconds=12),
        last=Decimal("11.4"),
        previous_close=Decimal("10"),
        session=TradingSession.RTH,
        updated_at=now - timedelta(seconds=12),
    )
    state.refresh(positions=[position], quotes=[quote])

    rows = state.equities_payload(now=now)
    assert len(rows) == 1
    row = rows[0]
    assert row["symbol"] == "AAPL"
    assert row["mark_source"] == "MID"
    assert row["previous_close"] == 10.0
    assert row["day_pnl"] == 300.0
    assert row["day_pnl_percent"] == 15.0
    assert row["day_pnl_pct"] == 15.0
    assert row["pnl_unrealized"] == 300.0
    assert row["pnl_unrealized_percent"] == 15.0
    assert row["pnl_unrealized_pct"] == 15.0
    assert row["total_pnl"] == 300.0
    assert row["total_pnl_percent"] == 15.0
    assert row["stale_seconds"] == 12


def test_equities_payload_percentages_handle_zero_denominators() -> None:
    state = PositionsState()
    instrument = Instrument(
        symbol="TSLA", instrument_type=InstrumentType.EQUITY, multiplier=Decimal("1")
    )
    position = Position(
        instrument=instrument, quantity=Decimal("50"), avg_cost=Decimal("0")
    )
    now = datetime(2024, 1, 2, 16, 0, tzinfo=UTC)
    quote = Quote(
        symbol="TSLA",
        bid=None,
        ask=None,
        last=Decimal("5"),
        last_ts=now,
        previous_close=None,
        session=TradingSession.ETH,
        updated_at=now,
    )
    state.refresh(positions=[position], quotes=[quote])

    rows = state.equities_payload(now=now)
    assert len(rows) == 1
    row = rows[0]
    assert row["day_pnl"] is None
    assert row["day_pnl_percent"] is None
    assert row["day_pnl_pct"] is None
    assert row["pnl_unrealized"] is None
    assert row["pnl_unrealized_percent"] is None
    assert row["pnl_unrealized_pct"] is None
    assert row["total_pnl"] is None
    assert row["total_pnl_percent"] is None


def test_equities_payload_skips_when_mark_missing() -> None:
    state = PositionsState()
    instrument = Instrument(
        symbol="SPY", instrument_type=InstrumentType.EQUITY, multiplier=Decimal("1")
    )
    position = Position(
        instrument=instrument, quantity=Decimal("25"), avg_cost=Decimal("100")
    )
    now = datetime(2024, 2, 1, 15, 0, tzinfo=UTC)
    quote = Quote(
        symbol="SPY",
        bid=None,
        ask=None,
        last=None,
        previous_close=None,
        session=TradingSession.RTH,
        updated_at=now,
    )
    state.refresh(positions=[position], quotes=[quote])

    rows = state.equities_payload(now=now)
    assert len(rows) == 1
    row = rows[0]
    assert row["day_pnl"] is None
    assert row["pnl_unrealized"] is None
    assert row["total_pnl"] is None


def test_positions_view_normalizes_last_close_mark_source_and_staleness() -> None:
    state = PositionsState()
    prev_close_ts = datetime(2024, 1, 2, 21, 0, tzinfo=UTC)
    positions_view = {
        "single_stocks": [
            {
                "symbol": "ABC",
                "qty": 10.0,
                "avg_cost": 100.0,
                "mark": 101.5,
                "mark_source": "LAST_CLOSE",
                "stale_seconds": 0,
                "previous_close_ts": prev_close_ts.isoformat(),
            }
        ],
        "option_combos": [],
        "single_options": [],
    }
    state.refresh(positions_view=positions_view)

    now = prev_close_ts + timedelta(hours=12)
    payload = state.positions_view_payload(now)

    stocks = payload.get("single_stocks")
    assert stocks, "expected at least one single stock entry"
    stock = stocks[0]
    assert stock["mark_source"] == "PREV"
    assert stock["price_source"] == "prev"
    assert stock["stale_seconds"] == int((now - prev_close_ts).total_seconds())
    assert stock["stale_s"] == stock["stale_seconds"]


def test_positions_view_prev_without_timestamp_uses_default_staleness() -> None:
    state = PositionsState()
    positions_view = {
        "single_stocks": [
            {
                "symbol": "XYZ",
                "qty": 5.0,
                "avg_cost": 50.0,
                "mark": 51.0,
                "mark_source": "LAST_CLOSE",
                "stale_seconds": 0,
            }
        ],
        "option_combos": [],
        "single_options": [],
    }
    state.refresh(positions_view=positions_view)

    now = datetime(2024, 1, 3, 13, 0, tzinfo=UTC)
    payload = state.positions_view_payload(now)

    stocks = payload.get("single_stocks")
    assert stocks, "expected at least one single stock entry"
    stock = stocks[0]
    assert stock["mark_source"] == "PREV"
    assert stock["stale_seconds"] == 0
