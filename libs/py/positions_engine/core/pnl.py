# SPDX-License-Identifier: MIT

"""P&L helpers for equities and option legs."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .models import Position


@dataclass(frozen=True)
class PnLBreakdown:
    """Simple container for day and total P&L figures."""

    day: Decimal
    total: Decimal


def equity_pnl(
    position: Position,
    mark: Decimal | None,
    previous_close: Decimal | None,
) -> PnLBreakdown:
    """Compute equity P&L using the provided mark."""

    basis = position.avg_cost
    if basis in (None, Decimal("0")):
        basis = None
    fallback_mark = basis if basis is not None else mark
    mark_value = _coerce_decimal(mark, fallback=fallback_mark)
    day = Decimal("0")
    if previous_close is not None:
        day = (mark_value - previous_close) * position.quantity * position.multiplier
    total = Decimal("0")
    if basis is not None:
        total = (mark_value - basis) * position.quantity * position.multiplier
    return PnLBreakdown(day=day, total=total)


def option_leg_pnl(
    position: Position,
    mark: Decimal | None,
    previous_close: Decimal | None,
) -> PnLBreakdown:
    """Alias for equity-style math (option multiplier lives on the instrument)."""

    return equity_pnl(position=position, mark=mark, previous_close=previous_close)


def _coerce_decimal(value: Decimal | None, fallback: Decimal | None) -> Decimal:
    if value is None:
        if fallback is not None:
            return fallback
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
