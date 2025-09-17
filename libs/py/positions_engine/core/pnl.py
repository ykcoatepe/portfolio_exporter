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

    mark_value = _coerce_decimal(mark, fallback=position.avg_cost)
    day = Decimal("0")
    if previous_close is not None:
        day = (mark_value - previous_close) * position.quantity * position.multiplier
    total = (mark_value - position.avg_cost) * position.quantity * position.multiplier
    return PnLBreakdown(day=day, total=total)


def option_leg_pnl(
    position: Position,
    mark: Decimal | None,
    previous_close: Decimal | None,
) -> PnLBreakdown:
    """Alias for equity-style math (option multiplier lives on the instrument)."""

    return equity_pnl(position=position, mark=mark, previous_close=previous_close)


def _coerce_decimal(value: Decimal | None, fallback: Decimal) -> Decimal:
    if value is None:
        return fallback
    return Decimal(value)
