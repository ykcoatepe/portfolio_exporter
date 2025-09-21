from __future__ import annotations

import logging
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


def _option(symbol: str, qty: str) -> Position:
    instrument = Instrument(
        symbol=symbol,
        instrument_type=InstrumentType.OPTION,
        multiplier=Decimal("100"),
    )
    return Position(
        instrument=instrument,
        quantity=Decimal(qty),
        avg_cost=Decimal("1.0"),
        metadata={"account": "TEST"},
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


def test_positions_view_augments_missing_combos(caplog) -> None:
    state = PositionsState()
    padded_symbol = "SPX  20241018C00460000"
    compact_symbol = "SPX20241018C00465000"
    option_positions = [
        _option(padded_symbol, "-1"),
        _option(compact_symbol, "1"),
    ]
    upstream_view = {
        "single_stocks": [],
        "option_combos": [],
        "single_options": [
            {
                "symbol": padded_symbol,
                "underlying": "SPX",
                "right": "CALL",
                "strike": 4600.0,
                "expiry": "2024-10-18",
                "quantity": -1.0,
            },
            {
                "symbol": compact_symbol,
                "underlying": "SPX",
                "right": "CALL",
                "strike": 4650.0,
                "expiry": "2024-10-18",
                "quantity": 1.0,
            },
        ],
    }

    state.refresh(positions=option_positions, positions_view=upstream_view, data_source="internal")

    now = datetime(2024, 1, 1, tzinfo=UTC)
    with caplog.at_level(logging.INFO):
        payload = state.positions_view_payload(now)

    combos = payload.get("option_combos") or []
    assert combos, "expected combos to be synthesized from single legs"
    combo_leg_symbols = {
        str(leg.get("symbol"))
        for combo in combos
        for leg in combo.get("legs", [])
        if isinstance(leg, dict)
    }
    assert combo_leg_symbols == {padded_symbol, compact_symbol}, "combo legs should keep original OSI"

    combo_groups = payload.get("combo_groups") or []
    assert combo_groups, "expected combo groups alongside combos"
    first_combo = combos[0]
    assert first_combo.get("combo_group_id"), "combo grouping metadata missing"
    assert first_combo.get("group_qty") is not None, "combo group quantity missing"

    returned_symbols = {
        str(leg.get("symbol"))
        for leg in payload.get("single_options") or []
        if isinstance(leg, dict)
    }
    expected_symbols = {leg["symbol"] for leg in upstream_view["single_options"]}
    assert returned_symbols == expected_symbols, "single leg payload should remain intact"

    snapshot_symbols = {
        str(leg.get("symbol"))
        for combo in (state.snapshot_payload(now)["positions_view"].get("option_combos") or [])
        for leg in combo.get("legs", [])
        if isinstance(leg, dict)
    }
    assert snapshot_symbols == {padded_symbol, compact_symbol}, "snapshot view should preserve OSI"

    assert any("grouped" in record.message for record in caplog.records)

    caplog.clear()
    with caplog.at_level(logging.INFO):
        payload_again = state.positions_view_payload(now)
    assert payload_again.get("option_combos")
    assert not any("grouped" in record.message for record in caplog.records), "log should fire once"
