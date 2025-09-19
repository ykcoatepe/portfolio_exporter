from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from positions_engine.combos import ComboStrategy, build_option_leg_snapshot, detect_option_combos
from positions_engine.core.marks import MarkSettings
from positions_engine.core.models import Instrument, InstrumentType, Position, Quote, TradingSession
from positions_engine.service.state import PositionsState


NOW = datetime(2024, 1, 5, 15, 30, tzinfo=UTC)
MARK_SETTINGS = MarkSettings()


def _make_instrument(symbol: str) -> Instrument:
    return Instrument(symbol=symbol, instrument_type=InstrumentType.OPTION, multiplier=Decimal("100"))


def _make_quote(symbol: str, bid: float = 1.0, ask: float = 1.2, last: float = 1.1) -> Quote:
    return Quote(
        symbol=symbol,
        bid=Decimal(str(bid)),
        ask=Decimal(str(ask)),
        last=Decimal(str(last)),
        previous_close=Decimal("1.0"),
        session=TradingSession.RTH,
        updated_at=NOW,
    )


def _build_leg(
    *,
    symbol: str,
    qty: float,
    avg_cost: float,
    metadata: dict[str, object] | None = None,
    quote: Quote | None = None,
) -> Position:
    instrument = _make_instrument(symbol)
    position = Position(
        instrument=instrument,
        quantity=Decimal(str(qty)),
        avg_cost=Decimal(str(avg_cost)),
        metadata=metadata or {},
    )
    return position, quote


def _snapshot(position: Position, quote: Quote | None = None):
    return build_option_leg_snapshot(position, quote, NOW, MARK_SETTINGS)


def test_build_option_leg_snapshot_parses_metadata() -> None:
    metadata = {
        "underlying": "AAPL",
        "expiry": "2024-01-19",
        "right": "C",
        "strike": Decimal("150"),
        "delta": Decimal("0.45"),
    }
    position, quote = _build_leg(
        symbol="AAPL  20240119C00150000",
        qty=1,
        avg_cost=1.5,
        metadata=metadata,
        quote=_make_quote("AAPL  20240119C00150000"),
    )
    leg = _snapshot(position, quote)
    assert leg is not None
    assert leg.underlying == "AAPL"
    assert leg.right == "CALL"
    assert leg.strike == Decimal("150")
    assert leg.dte >= 0
    assert leg.mark_source in {"MID", "LAST", "PREV", "MISSING"}
    assert leg.delta == Decimal("0.45")


def test_detect_vertical_combo() -> None:
    base_metadata = {
        "underlying": "TSLA",
        "expiry": "2024-03-15",
        "right": "C",
    }
    positions = [
        Position(
            instrument=_make_instrument("TSLA  20240315C00250000"),
            quantity=Decimal("1"),
            avg_cost=Decimal("2.0"),
            metadata={**base_metadata, "strike": Decimal("250")},
        ),
        Position(
            instrument=_make_instrument("TSLA  20240315C00260000"),
            quantity=Decimal("-1"),
            avg_cost=Decimal("1.2"),
            metadata={**base_metadata, "strike": Decimal("260")},
        ),
    ]
    legs = [build_option_leg_snapshot(pos, None, NOW, MARK_SETTINGS) for pos in positions]
    detection = detect_option_combos([leg for leg in legs if leg is not None])
    assert len(detection.combos) == 1
    combo = detection.combos[0]
    assert combo.strategy == ComboStrategy.VERTICAL
    assert not detection.orphans


def test_detect_calendar_combo() -> None:
    positions = [
        Position(
            instrument=_make_instrument("MSFT  20240315C00300000"),
            quantity=Decimal("1"),
            avg_cost=Decimal("3.5"),
            metadata={"underlying": "MSFT", "expiry": "2024-03-15", "right": "C", "strike": Decimal("300")},
        ),
        Position(
            instrument=_make_instrument("MSFT  20240419C00300000"),
            quantity=Decimal("-1"),
            avg_cost=Decimal("2.1"),
            metadata={"underlying": "MSFT", "expiry": "2024-04-19", "right": "C", "strike": Decimal("300")},
        ),
    ]
    legs = [build_option_leg_snapshot(pos, None, NOW, MARK_SETTINGS) for pos in positions]
    detection = detect_option_combos([leg for leg in legs if leg is not None])
    assert len(detection.combos) == 1
    assert detection.combos[0].strategy == ComboStrategy.CALENDAR


def test_detect_straddle_and_strangle() -> None:
    straddle_positions = [
        Position(
            instrument=_make_instrument("QQQ   20240216C00390000"),
            quantity=Decimal("1"),
            avg_cost=Decimal("1.8"),
            metadata={"underlying": "QQQ", "expiry": "2024-02-16", "right": "C", "strike": Decimal("390")},
        ),
        Position(
            instrument=_make_instrument("QQQ   20240216P00390000"),
            quantity=Decimal("1"),
            avg_cost=Decimal("2.0"),
            metadata={"underlying": "QQQ", "expiry": "2024-02-16", "right": "P", "strike": Decimal("390")},
        ),
    ]
    straddle_legs = [build_option_leg_snapshot(pos, None, NOW, MARK_SETTINGS) for pos in straddle_positions]
    detection_straddle = detect_option_combos([leg for leg in straddle_legs if leg is not None])
    assert detection_straddle.combos[0].strategy == ComboStrategy.STRADDLE

    strangle_positions = [
        Position(
            instrument=_make_instrument("QQQ   20240216C00395000"),
            quantity=Decimal("-1"),
            avg_cost=Decimal("1.0"),
            metadata={"underlying": "QQQ", "expiry": "2024-02-16", "right": "C", "strike": Decimal("395")},
        ),
        Position(
            instrument=_make_instrument("QQQ   20240216P00385000"),
            quantity=Decimal("-1"),
            avg_cost=Decimal("1.1"),
            metadata={"underlying": "QQQ", "expiry": "2024-02-16", "right": "P", "strike": Decimal("385")},
        ),
    ]
    strangle_legs = [build_option_leg_snapshot(pos, None, NOW, MARK_SETTINGS) for pos in strangle_positions]
    detection_strangle = detect_option_combos([leg for leg in strangle_legs if leg is not None])
    assert detection_strangle.combos[0].strategy == ComboStrategy.STRANGLE


def test_detect_iron_condor_combo() -> None:
    metadata = {"underlying": "SPY", "expiry": "2024-03-15"}
    positions = [
        Position(
            instrument=_make_instrument("SPY   20240315C00430000"),
            quantity=Decimal("-1"),
            avg_cost=Decimal("1.7"),
            metadata={**metadata, "right": "C", "strike": Decimal("430")},
        ),
        Position(
            instrument=_make_instrument("SPY   20240315C00435000"),
            quantity=Decimal("1"),
            avg_cost=Decimal("1.0"),
            metadata={**metadata, "right": "C", "strike": Decimal("435")},
        ),
        Position(
            instrument=_make_instrument("SPY   20240315P00410000"),
            quantity=Decimal("-1"),
            avg_cost=Decimal("1.5"),
            metadata={**metadata, "right": "P", "strike": Decimal("410")},
        ),
        Position(
            instrument=_make_instrument("SPY   20240315P00405000"),
            quantity=Decimal("1"),
            avg_cost=Decimal("0.9"),
            metadata={**metadata, "right": "P", "strike": Decimal("405")},
        ),
    ]
    legs = [build_option_leg_snapshot(pos, None, NOW, MARK_SETTINGS) for pos in positions]
    detection = detect_option_combos([leg for leg in legs if leg is not None])
    assert len(detection.combos) == 1
    assert detection.combos[0].strategy == ComboStrategy.IRON_CONDOR


def test_detect_ratio_combo() -> None:
    metadata = {"underlying": "AMD", "expiry": "2024-02-16", "right": "C"}
    positions = [
        Position(
            instrument=_make_instrument("AMD   20240216C00120000"),
            quantity=Decimal("2"),
            avg_cost=Decimal("0.8"),
            metadata={**metadata, "strike": Decimal("120")},
        ),
        Position(
            instrument=_make_instrument("AMD   20240216C00125000"),
            quantity=Decimal("-1"),
            avg_cost=Decimal("0.4"),
            metadata={**metadata, "strike": Decimal("125")},
        ),
    ]
    legs = [build_option_leg_snapshot(pos, None, NOW, MARK_SETTINGS) for pos in positions]
    detection = detect_option_combos([leg for leg in legs if leg is not None])
    assert detection.combos[0].strategy == ComboStrategy.RATIO


def test_options_payload_and_stats_integration() -> None:
    state = PositionsState()
    positions = []
    quotes = []

    # Vertical combo
    positions.append(
        Position(
            instrument=_make_instrument("TSLA  20240315C00250000"),
            quantity=Decimal("1"),
            avg_cost=Decimal("2.0"),
            metadata={"underlying": "TSLA", "expiry": "2024-03-15", "right": "C", "strike": Decimal("250")},
        )
    )
    positions.append(
        Position(
            instrument=_make_instrument("TSLA  20240315C00260000"),
            quantity=Decimal("-1"),
            avg_cost=Decimal("1.2"),
            metadata={"underlying": "TSLA", "expiry": "2024-03-15", "right": "C", "strike": Decimal("260")},
        )
    )

    # Orphan put
    positions.append(
        Position(
            instrument=_make_instrument("TSLA  20240315P00240000"),
            quantity=Decimal("-1"),
            avg_cost=Decimal("0.9"),
            metadata={"underlying": "TSLA", "expiry": "2024-03-15", "right": "P", "strike": Decimal("240")},
        )
    )

    for position in positions:
        quotes.append(_make_quote(position.instrument.symbol))

    state.refresh(positions=positions, quotes=quotes)

    payload = state.options_payload(now=NOW)
    assert payload["combos"]
    assert payload["legs"]  # orphan leg present

    stats = state.stats(now=NOW)
    assert stats["option_legs_count"] == 3
    assert stats["combos_matched"] == 1
    assert isinstance(stats["combos_detection_ms"], float)


def test_detection_performance_for_large_leg_set() -> None:
    legs: list[Position] = []
    for idx in range(250):
        underlying = f"SYM{idx:03d}"
        base_meta = {"underlying": underlying, "expiry": "2024-06-21", "right": "C"}
        legs.append(
            Position(
                instrument=_make_instrument(f"{underlying} 20240621C00{idx:02d}000"),
                quantity=Decimal("1"),
                avg_cost=Decimal("1.0"),
                metadata={**base_meta, "strike": Decimal(100 + idx)},
            )
        )
        legs.append(
            Position(
                instrument=_make_instrument(f"{underlying} 20240621C00{idx:02d}500"),
                quantity=Decimal("-1"),
                avg_cost=Decimal("0.6"),
                metadata={**base_meta, "strike": Decimal(105 + idx)},
            )
        )
    snapshots = [build_option_leg_snapshot(pos, None, NOW, MARK_SETTINGS) for pos in legs]
    detection = detect_option_combos([leg for leg in snapshots if leg is not None])
    assert len(detection.combos) == 250
    assert detection.detection_ms < 150.0
