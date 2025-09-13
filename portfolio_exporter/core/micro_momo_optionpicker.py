from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

from .micro_momo_types import ChainRow, ScanRow, Structure
from .micro_momo_utils import spread_pct


def _calls_by_strike(chain: Iterable[ChainRow]) -> Dict[float, ChainRow]:
    out: Dict[float, ChainRow] = {}
    for r in chain:
        if r.right.upper() == "C":
            out[r.strike] = r
    return dict(sorted(out.items()))


def _pick_expiry(chain: List[ChainRow]) -> Optional[str]:
    if not chain:
        return None
    # v1: single-file chain often has one expiry; just pick the first by sort
    expiries = sorted({r.expiry for r in chain})
    return expiries[0] if expiries else None


def _nearest_otm_call(price: float, calls: Dict[float, ChainRow]) -> Optional[ChainRow]:
    for strike, row in calls.items():
        if strike >= price:
            return row
    # fall back to the highest strike if all are ITM by this simple rule
    if calls:
        return list(calls.values())[-1]
    return None


def _call_at_strike(strike: float, calls: Dict[float, ChainRow]) -> Optional[ChainRow]:
    return calls.get(strike)


def pick_structure(
    scan: ScanRow,
    chain: List[ChainRow],
    direction: str,  # "long" | "short"
    cfg: Dict[str, object],
) -> Structure:
    expiry = _pick_expiry(chain)
    calls = _calls_by_strike(chain)

    min_width = float(cfg.get("options", {}).get("min_width", 5.0))  # type: ignore[union-attr]
    min_oi = int(cfg.get("liquidity", {}).get("min_oi", 50))  # type: ignore[union-attr]
    max_spread = float(cfg.get("options", {}).get("max_spread_pct", 0.25))  # type: ignore[union-attr]

    if not expiry or not calls:
        return Structure(
            template="Template",
            expiry=expiry,
            long_strike=None,
            short_strike=None,
            debit_or_credit=None,
            width=None,
            per_leg_oi_ok=False,
            per_leg_spread_pct=None,
            needs_chain=True,
            limit_price=None,
        )

    if direction == "long":
        # Debit call: buy ATM/OTM call, sell higher strike call (vertical debit)
        long_call = _nearest_otm_call(scan.price, calls)
        if not long_call:
            return Structure(
                template="Template",
                expiry=expiry,
                long_strike=None,
                short_strike=None,
                debit_or_credit=None,
                width=None,
                per_leg_oi_ok=False,
                per_leg_spread_pct=None,
                needs_chain=True,
                limit_price=None,
            )
        # find short strike at least min_width above
        short_strike = None
        for strike in sorted(calls):
            if strike >= long_call.strike + min_width:
                short_strike = strike
                break
        short_call = _call_at_strike(short_strike, calls) if short_strike else None
        if not short_call:
            return Structure(
                template="Template",
                expiry=expiry,
                long_strike=long_call.strike,
                short_strike=None,
                debit_or_credit=None,
                width=None,
                per_leg_oi_ok=False,
                per_leg_spread_pct=None,
                needs_chain=True,
                limit_price=None,
            )

        leg_spreads = [spread_pct(long_call.bid, long_call.ask), spread_pct(short_call.bid, short_call.ask)]
        # If any leg has no reliable spread, treat as failing spread check
        per_leg_spread = None
        if all(v is not None for v in leg_spreads):
            per_leg_spread = max([v for v in leg_spreads if v is not None])  # type: ignore[arg-type]
        oi_ok = long_call.oi >= min_oi and short_call.oi >= min_oi
        spread_ok = per_leg_spread is not None and per_leg_spread <= max_spread
        limit_price = max(0.01, long_call.mid - short_call.mid)
        return Structure(
            template="DebitCall",
            expiry=expiry,
            long_strike=long_call.strike,
            short_strike=short_call.strike,
            debit_or_credit="debit",
            width=abs(short_call.strike - long_call.strike),
            per_leg_oi_ok=bool(oi_ok),
            per_leg_spread_pct=per_leg_spread,
            needs_chain=not (oi_ok and spread_ok),
            limit_price=limit_price,
        )

    # Short direction: bear call credit (sell OTM call, buy further OTM call)
    short_call = _nearest_otm_call(scan.price, calls)
    if not short_call:
        return Structure(
            template="Template",
            expiry=expiry,
            long_strike=None,
            short_strike=None,
            debit_or_credit=None,
            width=None,
            per_leg_oi_ok=False,
            per_leg_spread_pct=None,
            needs_chain=True,
            limit_price=None,
        )
    long_protect = None
    for strike in sorted(calls):
        if strike >= short_call.strike + min_width:
            long_protect = calls[strike]
            break
    if not long_protect:
        return Structure(
            template="Template",
            expiry=expiry,
            long_strike=None,
            short_strike=short_call.strike,
            debit_or_credit=None,
            width=None,
            per_leg_oi_ok=False,
            per_leg_spread_pct=None,
            needs_chain=True,
            limit_price=None,
        )

    leg_spreads2 = [spread_pct(short_call.bid, short_call.ask), spread_pct(long_protect.bid, long_protect.ask)]
    per_leg_spread2 = None
    if all(v is not None for v in leg_spreads2):
        per_leg_spread2 = max([v for v in leg_spreads2 if v is not None])  # type: ignore[arg-type]
    oi_ok2 = short_call.oi >= min_oi and long_protect.oi >= min_oi
    spread_ok2 = per_leg_spread2 is not None and per_leg_spread2 <= max_spread
    limit_price2 = max(0.01, short_call.mid - long_protect.mid)
    return Structure(
        template="BearCallCredit",
        expiry=expiry,
        long_strike=long_protect.strike,
        short_strike=short_call.strike,
        debit_or_credit="credit",
        width=abs(long_protect.strike - short_call.strike),
        per_leg_oi_ok=bool(oi_ok2),
        per_leg_spread_pct=per_leg_spread2,
        needs_chain=not (oi_ok2 and spread_ok2),
        limit_price=limit_price2,
    )

