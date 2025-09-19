"""Exposure analytics (v0.1).

Delta-beta exposure combines equity beta exposure and option delta exposure
normalized by NAV.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..models import Position


def delta_beta_exposure(positions: Iterable[Position], nav: float) -> float:
    if nav <= 0:
        return 0.0
    eq_expo = 0.0
    opt_expo = 0.0
    for p in positions:
        if p.kind == "equity":
            beta = float(p.beta or 1.0)
            if p.mark is None:
                continue
            eq_expo += beta * (p.qty * float(p.mark))
            continue
        # Option exposure approximates delta-adjusted underlying notional. Prefer the
        # carrying position mark (underlying last) and fall back to strike when
        # a live quote is unavailable to avoid understating risk.
        underlying_mark = 0.0
        try:
            if p.mark is not None:
                underlying_mark = float(p.mark)
            else:
                underlying_mark = 0.0
        except Exception:
            underlying_mark = 0.0
        for leg in p.legs or []:
            delta = leg.delta
            if delta is None:
                continue
            notional = underlying_mark
            if notional <= 0:
                try:
                    notional = float(leg.strike)
                except Exception:
                    notional = 0.0
            if notional <= 0:
                continue
            opt_expo += float(delta) * 100.0 * notional * int(leg.qty)
    total = (eq_expo + opt_expo) / float(nav)
    return float(total)
