from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from positions_engine.combos import (
    ComboStrategy,
    build_option_leg_snapshot,
    detect_option_combos,
    group_option_combos,
)
from positions_engine.core.marks import MarkSettings
from positions_engine.core.models import Instrument, InstrumentType, Position
from positions_engine.ingest.internal import InternalScriptsProvider

NOW = datetime(2024, 10, 1, 15, 30, tzinfo=UTC)
MARK_SETTINGS = MarkSettings()
OSI_PATTERN = re.compile(r"\d{6,8}[CP]\d{8}")


def _make_instrument(symbol: str) -> Instrument:
    return Instrument(
        symbol=symbol, instrument_type=InstrumentType.OPTION, multiplier=Decimal("100")
    )


def _make_position(symbol: str, qty: float) -> Position:
    return Position(
        instrument=_make_instrument(symbol),
        quantity=Decimal(str(qty)),
        avg_cost=Decimal("1.0"),
        metadata={},
    )


def test_internal_option_leg_record_populates_osi_fields() -> None:
    provider = InternalScriptsProvider()
    leg = {"symbol": "QQQ 251220P00380000", "quantity": -5}

    record, quote = provider._option_leg_record(leg, fallback_underlying=None)

    assert quote is None
    assert record is not None
    assert record["underlying"] == "QQQ"
    assert record["right"] == "PUT"
    assert record["expiry"] == "2025-12-20"
    assert record["multiplier"] == 100
    assert record["strike"] == pytest.approx(380.0)


def test_osi_parsing_enables_combo_grouping() -> None:
    positions = [
        _make_position("SPY 251017P00390000", -10),
        _make_position("SPY 251017P00380000", 10),
        _make_position("SPY251017C00420000", -10),
        _make_position("SPY251017C00430000", 10),
    ]

    snapshots = [
        build_option_leg_snapshot(position, None, NOW, MARK_SETTINGS)
        for position in positions
    ]
    legs = [leg for leg in snapshots if leg is not None]

    assert len(legs) == len(positions)

    detection = detect_option_combos(legs)
    assert detection.combos, "expected combo detection from OSI-only legs"
    assert all(combo.underlying == "SPY" for combo in detection.combos)
    assert ComboStrategy.IRON_CONDOR in {combo.strategy for combo in detection.combos}

    grouped = group_option_combos(detection.combos)
    assert grouped.groups, "expected grouped combos"

    group_payload = grouped.groups[0].to_payload()
    assert group_payload["combo_group_id"]
    assert group_payload["group_qty"] is not None
    assert group_payload["label"]
    assert not OSI_PATTERN.search(group_payload["display"]["combo_label"])

    assert group_payload["legs"], "group legs should not be empty"
    for leg in group_payload["legs"]:
        assert leg["combo_group_id"] == group_payload["combo_group_id"]
        assert str(leg["right"]).upper().startswith(("C", "P"))
        assert leg["expiry"] == "2025-10-17"
        assert not OSI_PATTERN.search(leg["display"]["leg_label"])
