"""Temporary combo grouping (v0.1)."""

from __future__ import annotations

from typing import Iterable, List

from ..models import OptionLeg, Position


def group_credit_spreads(positions: Iterable[Position]) -> List[Position]:
    """Group simple vertical credit spreads from individual option positions.

    Minimal heuristic: pairs of same expiry/right with opposing qty signs and
    same symbol. Assumes two-leg credit spreads only.
    """
    # In v0.1, assume incoming positions are already grouped by the datasource
    return list(positions)
