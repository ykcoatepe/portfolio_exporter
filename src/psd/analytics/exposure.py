"""Exposure analytics (v0.1).

Delta-beta exposure combines equity beta exposure and option delta exposure
normalized by NAV.
"""

from __future__ import annotations

from typing import Iterable

from ..models import Position


def delta_beta_exposure(positions: Iterable[Position], nav: float) -> float:
    if nav <= 0:
        return 0.0
    eq_expo = 0.0
    opt_expo = 0.0
    for p in positions:
        if p.kind == "equity":
            beta = float(p.beta or 1.0)
            eq_expo += beta * (p.qty * p.mark)
        else:
            # Sum option delta exposure across legs
            for leg in p.legs:
                d = leg.delta or 0.0
                opt_expo += d * 100.0 * leg.price * leg.qty
    total = (eq_expo + opt_expo) / float(nav)
    return float(total)
