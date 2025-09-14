"""Robust combo recognition (v0.2).

Groups option credit spreads (bear call, bull put) and iron condors.
Rules:
- Same underlying and expiry across legs.
- For condor: short strikes inside, long strikes outside; net credit > 0.
- Computes widths, net credit, max loss per side and overall. Provides to_dict().
"""

from __future__ import annotations

from typing import Iterable, List, Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, timezone

from ..models import OptionLeg, Position


@dataclass(slots=True)
class Combo:
    kind: str  # 'credit_spread' or 'iron_condor'
    symbol: str
    expiry: str  # YYYYMMDD
    short_calls: List[OptionLeg]
    long_calls: List[OptionLeg]
    short_puts: List[OptionLeg]
    long_puts: List[OptionLeg]
    width_call: float
    width_put: float
    credit: float
    max_loss: float
    dte: int

    def to_dict(self) -> Dict[str, object]:
        return {
            "kind": self.kind,
            "symbol": self.symbol,
            "expiry": self.expiry,
            "short_calls": [(l.strike, l.qty) for l in self.short_calls],
            "long_calls": [(l.strike, l.qty) for l in self.long_calls],
            "short_puts": [(l.strike, l.qty) for l in self.short_puts],
            "long_puts": [(l.strike, l.qty) for l in self.long_puts],
            "width_call": self.width_call,
            "width_put": self.width_put,
            "credit": round(self.credit, 4),
            "max_loss": round(self.max_loss, 4),
            "dte": self.dte,
        }


def _dte(expiry_yyyymmdd: str) -> int:
    try:
        dt = datetime.strptime(expiry_yyyymmdd, "%Y%m%d").replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return max(0, (dt.date() - now.date()).days)
    except Exception:
        return 0


def _pair_vertical(shorts: List[OptionLeg], longs: List[OptionLeg], side: str) -> Tuple[Optional[Tuple[OptionLeg, OptionLeg, int]], float, float]:
    """Pick a single-quantity vertical credit pair and return (legs, width, credit_per_contract).

    Returns ((short, long, contracts), width, credit) or (None, 0, 0) if unavailable.
    """
    # Choose first feasible pair by strike ordering for credit spreads
    for s in shorts:
        for l in longs:
            if s.expiry != l.expiry:
                continue
            if side == "C" and s.strike < l.strike:
                contracts = max(0, min(abs(s.qty), abs(l.qty)))
                if contracts == 0:
                    continue
                credit = float(s.price) - float(l.price)
                if credit <= 0:
                    continue
                width = float(l.strike) - float(s.strike)
                if width <= 0:
                    continue
                return (s, l, contracts), width, credit
            if side == "P" and s.strike > l.strike:
                contracts = max(0, min(abs(s.qty), abs(l.qty)))
                if contracts == 0:
                    continue
                credit = float(s.price) - float(l.price)
                if credit <= 0:
                    continue
                width = float(s.strike) - float(l.strike)
                if width <= 0:
                    continue
                return (s, l, contracts), width, credit
    return None, 0.0, 0.0


def recognize(positions: Iterable[Position]) -> Tuple[List[Combo], List[Dict[str, str]]]:
    """Return combos and orphan-risk warnings from option legs in positions.

    Only uses Position.kind == 'option' legs; other kinds are forwarded unchanged elsewhere.
    """
    # Flatten legs by (symbol, expiry)
    by_key: Dict[Tuple[str, str], Dict[str, List[OptionLeg]]] = {}
    orphans: List[Dict[str, str]] = []
    for p in positions:
        for leg in (p.legs or []):
            key = (leg.symbol, leg.expiry)
            bucket = by_key.setdefault(key, {"C_short": [], "C_long": [], "P_short": [], "P_long": []})
            if leg.right == "C":
                (bucket["C_short"] if leg.qty < 0 else bucket["C_long"]).append(leg)
            else:
                (bucket["P_short"] if leg.qty < 0 else bucket["P_long"]).append(leg)

    combos: List[Combo] = []
    for (sym, exp), b in by_key.items():
        pair_c, w_c, cr_c = _pair_vertical(b["C_short"], b["C_long"], "C")
        pair_p, w_p, cr_p = _pair_vertical(b["P_short"], b["P_long"], "P")
        dte = _dte(exp)
        total_credit = 0.0
        total_max_loss = 0.0
        if pair_c and pair_p:
            # Iron condor – sum side losses
            total_credit = cr_c + cr_p
            loss_c = (w_c - cr_c) * 100 * pair_c[2]
            loss_p = (w_p - cr_p) * 100 * pair_p[2]
            total_max_loss = max(loss_c, loss_p)
            combos.append(
                Combo(
                    kind="iron_condor",
                    symbol=sym,
                    expiry=exp,
                    short_calls=[pair_c[0]],
                    long_calls=[pair_c[1]],
                    short_puts=[pair_p[0]],
                    long_puts=[pair_p[1]],
                    width_call=w_c,
                    width_put=w_p,
                    credit=total_credit,
                    max_loss=total_max_loss,
                    dte=dte,
                )
            )
        elif pair_c:
            total_credit = cr_c
            total_max_loss = (w_c - cr_c) * 100 * pair_c[2]
            combos.append(
                Combo(
                    kind="credit_spread",
                    symbol=sym,
                    expiry=exp,
                    short_calls=[pair_c[0]],
                    long_calls=[pair_c[1]],
                    short_puts=[],
                    long_puts=[],
                    width_call=w_c,
                    width_put=0.0,
                    credit=total_credit,
                    max_loss=total_max_loss,
                    dte=dte,
                )
            )
        elif pair_p:
            total_credit = cr_p
            total_max_loss = (w_p - cr_p) * 100 * pair_p[2]
            combos.append(
                Combo(
                    kind="credit_spread",
                    symbol=sym,
                    expiry=exp,
                    short_calls=[],
                    long_calls=[],
                    short_puts=[pair_p[0]],
                    long_puts=[pair_p[1]],
                    width_call=0.0,
                    width_put=w_p,
                    credit=total_credit,
                    max_loss=total_max_loss,
                    dte=dte,
                )
            )
        # orphan short without hedge on any side not forming a pair
        if not pair_c and b["C_short"] and not b["C_long"]:
            orphans.append({"symbol": sym, "expiry": exp, "side": "C", "reason": "orphan-risk"})
        if not pair_p and b["P_short"] and not b["P_long"]:
            orphans.append({"symbol": sym, "expiry": exp, "side": "P", "reason": "orphan-risk"})
    return combos, orphans
