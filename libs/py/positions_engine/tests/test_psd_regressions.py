# SPDX-License-Identifier: MIT

"""Regression tests for PSD cost basis, staleness, and leg mark handling."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from positions_engine.core.models import (
    Instrument,
    InstrumentType,
    Position,
    Quote,
    TradingSession,
)
from positions_engine.ingest.internal import InternalScriptsProvider
from positions_engine.service.normalize import compute_equity_pnl_fields
from positions_engine.service.state import (
    PositionsState,
    _normalize_option_mark_payload,
    _resolve_option_stale_seconds_entry,
)


def test_refresh_live_snapshot_preserves_existing_avg_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Incoming snapshots without avg_cost should keep the previous basis."""

    state = PositionsState()
    instrument = Instrument(symbol="AAPL", instrument_type=InstrumentType.EQUITY)
    initial_position = Position(
        instrument=instrument,
        quantity=Decimal("10"),
        avg_cost=Decimal("123.45"),
    )
    initial_quote = Quote(
        symbol="AAPL", last=Decimal("150"), session=TradingSession.RTH
    )
    state.refresh(
        positions=[initial_position],
        quotes=[initial_quote],
        snapshot_at=datetime.now(tz=UTC),
    )

    now = datetime.now(tz=UTC)
    positions_records = [
        {
            "symbol": "AAPL",
            "instrument_type": "equity",
            "quantity": 10,
            "multiplier": 1,
        }
    ]
    quotes_records = [
        {
            "symbol": "AAPL",
            "last": 151,
            "previous_close": 150,
            "session": TradingSession.RTH.value,
            "updated_at": now.isoformat(),
        }
    ]

    monkeypatch.setattr(
        InternalScriptsProvider,
        "load",
        lambda self: (positions_records, quotes_records),
    )

    state.refresh_live_snapshot()

    updated_position = state._positions["AAPL"]
    assert updated_position.avg_cost == Decimal("123.45")


def test_missing_basis_skips_total_pnl() -> None:
    instrument = Instrument(symbol="MSFT", instrument_type=InstrumentType.EQUITY)
    position = Position(instrument=instrument, quantity=Decimal("5"), avg_cost=None)
    result = compute_equity_pnl_fields(
        position=position,
        mark=Decimal("210"),
        previous_close=Decimal("205"),
    )
    assert result["day_pnl"] == pytest.approx(25.0)
    assert result["total_pnl"] is None


def test_last_close_alias_preserves_timestamp() -> None:
    now = datetime(2025, 9, 24, 9, 30, tzinfo=UTC)
    ten_minutes_ago = now - timedelta(minutes=10)
    entry = {
        "symbol": "AAPL",
        "mark_source": "LAST_CLOSE",
        "last_close_ts": ten_minutes_ago.isoformat(),
        "previous_close": "150.00",
    }

    normalized = _normalize_option_mark_payload(entry, now=now)
    assert normalized["mark_source"] == "PREV"
    assert "previous_close_ts" in normalized

    stale_seconds = _resolve_option_stale_seconds_entry(normalized, "PREV", now)
    assert stale_seconds == 600


def test_option_leg_rebuilds_mark_from_last_and_previous_close() -> None:
    provider = InternalScriptsProvider()

    leg_with_last = {
        "symbol": "AAPL  250118C00150000",
        "quantity": 1,
        "right": "CALL",
        "strike": 150,
        "expiry": "2025-01-18",
        "last": 1.23,
        "previous_close": 1.10,
    }
    record_last, quote_last = provider._option_leg_record(
        leg_with_last, fallback_underlying="AAPL"
    )
    assert record_last is not None
    assert quote_last is not None
    assert quote_last["last"] == pytest.approx(1.23)
    assert quote_last["mark"] == pytest.approx(1.23)

    leg_with_prev = {
        "symbol": "AAPL  250118C00150000",
        "quantity": 1,
        "right": "CALL",
        "strike": 150,
        "expiry": "2025-01-18",
        "previous_close": 0.95,
    }
    record_prev, quote_prev = provider._option_leg_record(
        leg_with_prev, fallback_underlying="AAPL"
    )
    assert record_prev is not None
    assert quote_prev is not None
    assert quote_prev["last"] == pytest.approx(0.95)
    assert quote_prev["mark"] == pytest.approx(0.95)
