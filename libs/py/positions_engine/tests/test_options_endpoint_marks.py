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


def _make_option_position(symbol: str = "AAPL  240517C00200000") -> Position:
    instrument = Instrument(
        symbol=symbol,
        instrument_type=InstrumentType.OPTION,
        multiplier=Decimal("100"),
    )
    return Position(
        instrument=instrument,
        quantity=Decimal("1"),
        avg_cost=Decimal("2.50"),
        metadata={
            "account": "acct-1",
            "underlying": "AAPL",
            "expiry": "2024-05-17",
            "right": "CALL",
            "strike": "200",
        },
    )


def test_leg_last_close_normalized_to_prev() -> None:
    now = datetime(2025, 5, 1, 15, 30, tzinfo=UTC)
    state = PositionsState()
    position = _make_option_position()
    quote = Quote(
        symbol=position.instrument.symbol,
        previous_close=Decimal("2.40"),
        previous_close_ts=now - timedelta(hours=1),
        session=TradingSession.CLOSED,
        updated_at=now - timedelta(minutes=5),
    )
    state.refresh(positions=[position], quotes=[quote], snapshot_at=now)

    payload = state.options_payload(now=now)
    leg = payload["legs"][0]

    assert leg["mark_source"] == "PREV"
    assert isinstance(leg["stale_seconds"], (int, float))
    assert leg["stale_seconds"] >= 3600


def test_leg_mid_uses_bid_ask_timestamps_for_staleness() -> None:
    now = datetime(2025, 5, 1, 15, 30, tzinfo=UTC)
    state = PositionsState()
    position = _make_option_position("AAPL  240517C00195000")
    quote = Quote(
        symbol=position.instrument.symbol,
        bid=Decimal("2.10"),
        bid_ts=now - timedelta(seconds=40),
        ask=Decimal("2.30"),
        ask_ts=now - timedelta(seconds=10),
        session=TradingSession.RTH,
        updated_at=now - timedelta(seconds=5),
    )
    state.refresh(positions=[position], quotes=[quote], snapshot_at=now)

    payload = state.options_payload(now=now)
    leg = payload["legs"][0]

    assert leg["mark_source"] == "MID"
    assert leg["stale_seconds"] == 10


def test_leg_missing_timestamps_uses_fallback_staleness() -> None:
    now = datetime(2025, 5, 1, 15, 30, tzinfo=UTC)
    state = PositionsState()
    position = _make_option_position("AAPL  240517P00200000")
    quote = Quote(
        symbol=position.instrument.symbol,
        previous_close=Decimal("2.75"),
        session=TradingSession.RTH,
        updated_at=now - timedelta(minutes=1),
    )
    state.refresh(positions=[position], quotes=[quote], snapshot_at=now)

    payload = state.options_payload(now=now)
    leg = payload["legs"][0]

    assert leg["mark_source"] == "PREV"
    assert leg["stale_seconds"] >= 23 * 3600
