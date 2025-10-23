# SPDX-License-Identifier: MIT

"""Strategy taxonomy helpers for option combo detection."""

from __future__ import annotations

from enum import Enum


class ComboStrategy(str, Enum):
    """Supported combo strategy labels."""

    VERTICAL = "VERTICAL"
    CALENDAR = "CALENDAR"
    STRADDLE = "STRADDLE"
    STRANGLE = "STRANGLE"
    IRON_CONDOR = "IRON_CONDOR"
    IRON_BUTTERFLY = "IRON_BUTTERFLY"
    RATIO = "RATIO"
    UNKNOWN = "UNKNOWN"


_STRATEGY_LABELS: dict[ComboStrategy, str] = {
    ComboStrategy.VERTICAL: "Vertical Spread",
    ComboStrategy.CALENDAR: "Calendar Spread",
    ComboStrategy.STRADDLE: "Straddle",
    ComboStrategy.STRANGLE: "Strangle",
    ComboStrategy.IRON_CONDOR: "Iron Condor",
    ComboStrategy.IRON_BUTTERFLY: "Iron Butterfly",
    ComboStrategy.RATIO: "Ratio Spread",
    ComboStrategy.UNKNOWN: "Unknown",
}


def strategy_label(strategy: ComboStrategy) -> str:
    """Return a human-friendly label for the combo strategy."""

    return _STRATEGY_LABELS.get(strategy, "Unknown")
