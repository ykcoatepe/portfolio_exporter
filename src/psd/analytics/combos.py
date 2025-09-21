"""Robust combo recognition (v0.2).

Groups option credit spreads (bear call, bull put) and iron condors.
Rules:
- Same underlying and expiry across legs.
- For condor: short strikes inside, long strikes outside; net credit > 0.
- Computes widths, net credit, max loss per side and overall. Provides to_dict().
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from ..models import OptionLeg, Position


@dataclass(slots=True)
class Combo:
    kind: str  # 'credit_spread' or 'iron_condor'
    symbol: str
    expiry: str  # YYYYMMDD
    short_calls: list[OptionLeg]
    long_calls: list[OptionLeg]
    short_puts: list[OptionLeg]
    long_puts: list[OptionLeg]
    width_call: float
    width_put: float
    credit: float
    max_loss: float
    dte: int

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "symbol": self.symbol,
            "expiry": self.expiry,
            "short_calls": [(leg.strike, leg.qty) for leg in self.short_calls],
            "long_calls": [(leg.strike, leg.qty) for leg in self.long_calls],
            "short_puts": [(leg.strike, leg.qty) for leg in self.short_puts],
            "long_puts": [(leg.strike, leg.qty) for leg in self.long_puts],
            "width_call": self.width_call,
            "width_put": self.width_put,
            "credit": round(self.credit, 4),
            "max_loss": round(self.max_loss, 4),
            "dte": self.dte,
        }


def _dte(expiry_yyyymmdd: str) -> int:
    try:
        dt = datetime.strptime(expiry_yyyymmdd, "%Y%m%d").replace(tzinfo=UTC)
        now = datetime.now(UTC)
        return max(0, (dt.date() - now.date()).days)
    except Exception:
        return 0


def _pair_vertical(
    shorts: list[OptionLeg], longs: list[OptionLeg], side: str
) -> tuple[tuple[OptionLeg, OptionLeg, int] | None, float, float]:
    """Pick a single-quantity vertical credit pair and return (legs, width, credit_per_contract).

    Returns ((short, long, contracts), width, credit) or (None, 0, 0) if unavailable.
    """
    # Choose first feasible pair by strike ordering for credit spreads
    for short_leg in shorts:
        for long_leg in longs:
            if short_leg.expiry != long_leg.expiry:
                continue
            if side == "C" and short_leg.strike < long_leg.strike:
                contracts = max(0, min(abs(short_leg.qty), abs(long_leg.qty)))
                if contracts == 0:
                    continue
                credit = float(short_leg.price) - float(long_leg.price)
                if credit <= 0:
                    continue
                width = float(long_leg.strike) - float(short_leg.strike)
                if width <= 0:
                    continue
                return (short_leg, long_leg, contracts), width, credit
            if side == "P" and short_leg.strike > long_leg.strike:
                contracts = max(0, min(abs(short_leg.qty), abs(long_leg.qty)))
                if contracts == 0:
                    continue
                credit = float(short_leg.price) - float(long_leg.price)
                if credit <= 0:
                    continue
                width = float(short_leg.strike) - float(long_leg.strike)
                if width <= 0:
                    continue
                return (short_leg, long_leg, contracts), width, credit
    return None, 0.0, 0.0


def recognize(positions: Iterable[Position]) -> tuple[list[Combo], list[dict[str, str]]]:
    """Return combos and orphan-risk warnings from option legs in positions.

    Only uses Position.kind == 'option' legs; other kinds are forwarded unchanged elsewhere.
    """
    # Flatten legs by (symbol, expiry)
    by_key: dict[tuple[str, str], dict[str, list[OptionLeg]]] = {}
    orphans: list[dict[str, str]] = []
    for p in positions:
        for leg in p.legs or []:
            key = (leg.symbol, leg.expiry)
            bucket = by_key.setdefault(key, {"C_short": [], "C_long": [], "P_short": [], "P_long": []})
            if leg.right == "C":
                (bucket["C_short"] if leg.qty < 0 else bucket["C_long"]).append(leg)
            else:
                (bucket["P_short"] if leg.qty < 0 else bucket["P_long"]).append(leg)

    combos: list[Combo] = []
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
        # orphan short without hedge for any unmatched quantity on each side
        short_call_qty = sum(abs(leg.qty) for leg in b["C_short"])
        long_call_qty = sum(abs(leg.qty) for leg in b["C_long"])
        if short_call_qty > max(long_call_qty, 0):
            matched = min(short_call_qty, long_call_qty)
            if short_call_qty - matched > 0:
                orphans.append({"symbol": sym, "expiry": exp, "side": "C", "reason": "orphan-risk"})
        short_put_qty = sum(abs(leg.qty) for leg in b["P_short"])
        long_put_qty = sum(abs(leg.qty) for leg in b["P_long"])
        if short_put_qty > max(long_put_qty, 0):
            matched = min(short_put_qty, long_put_qty)
            if short_put_qty - matched > 0:
                orphans.append({"symbol": sym, "expiry": exp, "side": "P", "reason": "orphan-risk"})
    return combos, orphans
