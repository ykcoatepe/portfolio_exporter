# SPDX-License-Identifier: MIT

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from positions_engine.core.models import Instrument, InstrumentType, Position, Quote, TradingSession
from positions_engine.service.state import PositionsState


def test_equities_payload_emits_pnl_and_percentages() -> None:
    state = PositionsState()
    instrument = Instrument(symbol="AAPL", instrument_type=InstrumentType.EQUITY, multiplier=Decimal("1"))
    position = Position(instrument=instrument, quantity=Decimal("200"), avg_cost=Decimal("10"))
    now = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
    quote = Quote(
        symbol="AAPL",
        bid=Decimal("11"),
        ask=Decimal("12"),
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
    assert row["day_pnl"] == 300.0
    assert row["total_pnl"] == 300.0
    assert row["day_pnl_percent"] == 15.0
    assert row["total_pnl_percent"] == 15.0
    assert row["stale_seconds"] == 12


def test_equities_payload_percentages_handle_zero_denominators() -> None:
    state = PositionsState()
    instrument = Instrument(symbol="TSLA", instrument_type=InstrumentType.EQUITY, multiplier=Decimal("1"))
    position = Position(instrument=instrument, quantity=Decimal("50"), avg_cost=Decimal("0"))
    now = datetime(2024, 1, 2, 16, 0, tzinfo=UTC)
    quote = Quote(
        symbol="TSLA",
        bid=None,
        ask=None,
        last=Decimal("5"),
        previous_close=None,
        session=TradingSession.ETH,
        updated_at=now,
    )
    state.refresh(positions=[position], quotes=[quote])

    rows = state.equities_payload(now=now)
    assert len(rows) == 1
    row = rows[0]
    assert row["day_pnl_percent"] is None
    assert row["total_pnl_percent"] is None
