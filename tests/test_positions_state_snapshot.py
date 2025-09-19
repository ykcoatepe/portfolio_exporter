from __future__ import annotations

from datetime import UTC, datetime, timezone
from decimal import Decimal

from positions_engine.core.models import Instrument, InstrumentType, Position, Quote
from positions_engine.service.state import PositionsState


def _equity(symbol: str) -> Position:
    return Position(
        instrument=Instrument(symbol=symbol, instrument_type=InstrumentType.EQUITY),
        quantity=Decimal("10"),
        avg_cost=Decimal("100"),
    )


def test_snapshot_updated_at_returns_latest_quote() -> None:
    state = PositionsState()
    positions = [_equity("AAPL"), _equity("MSFT")]
    quotes = [
        Quote(symbol="AAPL", bid=Decimal("1"), ask=Decimal("2"), updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc)),
        Quote(symbol="MSFT", bid=Decimal("1"), ask=Decimal("2"), updated_at=datetime(2024, 1, 2, tzinfo=timezone.utc)),
    ]

    state.refresh(positions=positions, quotes=quotes)

    assert state.snapshot_updated_at() == datetime(2024, 1, 2, tzinfo=timezone.utc)


def test_snapshot_updated_at_handles_naive_datetimes() -> None:
    state = PositionsState()
    positions = [_equity("SPY")]
    quotes = [
        Quote(symbol="SPY", bid=Decimal("1"), ask=Decimal("2"), updated_at=datetime(2024, 2, 1, 15, 30)),
    ]

    state.refresh(positions=positions, quotes=quotes)

    snapshot = state.snapshot_updated_at()
    assert snapshot is not None
    assert snapshot.tzinfo == timezone.utc
    assert snapshot.hour == 15
    assert snapshot.minute == 30


def test_snapshot_updated_at_uses_override_when_provided() -> None:
    state = PositionsState()
    override = datetime(2024, 3, 1, 14, 0, tzinfo=UTC)

    state.refresh(snapshot_at=override)

    assert state.snapshot_updated_at() == override
