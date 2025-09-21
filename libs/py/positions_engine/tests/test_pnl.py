# SPDX-License-Identifier: MIT

from __future__ import annotations

from decimal import Decimal

from positions_engine.core.models import Instrument, InstrumentType, Position
from positions_engine.core.pnl import equity_pnl


def test_equity_pnl_matches_expected_example() -> None:
    instrument = Instrument(symbol="AAPL", instrument_type=InstrumentType.EQUITY)
    position = Position(instrument=instrument, quantity=Decimal("200"), avg_cost=Decimal("10"))
    pnl = equity_pnl(position=position, mark=Decimal("11.5"), previous_close=Decimal("10"))
    assert pnl.day == Decimal("300")
    assert pnl.total == Decimal("300")


def test_equity_pnl_handles_missing_mark() -> None:
    instrument = Instrument(symbol="QQQ", instrument_type=InstrumentType.EQUITY)
    position = Position(instrument=instrument, quantity=Decimal("10"), avg_cost=Decimal("50"))
    pnl = equity_pnl(position=position, mark=None, previous_close=None)
    assert pnl.day == Decimal("0")
    assert pnl.total == Decimal("0")
