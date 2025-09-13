from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from .micro_momo_types import ChainRow, ScanRow, Structure
from .micro_momo_utils import spread_pct


def _calls_by_strike(chain: Iterable[Any]) -> Dict[float, Any]:
    out: Dict[float, ChainRow] = {}
    for r in chain:
        right = _get(r, "right", "").upper()
        if right == "C":
            out[float(_get(r, "strike", 0.0))] = r
    return dict(sorted(out.items()))


def _pick_expiry(chain: List[Any]) -> Optional[str]:
    if not chain:
        return None
    # v1: single-file chain often has one expiry; just pick the first by sort
    expiries = sorted({_get(r, "expiry") for r in chain if _get(r, "expiry")})
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


def _get(r: Any, name: str, default: Any = None) -> Any:
    return getattr(r, name, default) if not isinstance(r, dict) else r.get(name, default)


def pick_bull_put_credit(
    spot: float,
    chain: List[Any],
    expiry: Optional[str],
    cfg: Dict[str, object],
) -> Structure:
    if not chain or not expiry or spot <= 0:
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
    min_oi = int(cfg.get("liquidity", {}).get("min_oi", 50))  # type: ignore[union-attr]
    max_spread = float(cfg.get("options", {}).get("max_spread_pct", 0.25))  # type: ignore[union-attr]
    credit_ratio = float(cfg.get("options", {}).get("credit_min_collect_ratio", 0.3))  # type: ignore[union-attr]

    # Filter puts roughly near delta 0.2-0.25; if no delta, fallback to 5-15% OTM
    puts = [r for r in chain if str(_get(r, "right", "")).upper().startswith("P")]
    candidates: List[Tuple[float, Any]] = []
    for r in puts:
        strike = float(_get(r, "strike", 0.0))
        delta = _get(r, "delta", None)
        if delta is not None:
            d = abs(float(delta))
            if 0.18 <= d <= 0.30:
                candidates.append((strike, r))
        else:
            if spot * 0.85 <= strike <= spot * 0.97:
                candidates.append((strike, r))
    candidates.sort(key=lambda x: abs(x[0] - spot * 0.9))
    if not candidates:
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
    short_put = candidates[0][1]
    # Long put 3-8% lower
    long_target = float(_get(short_put, "strike", 0.0)) * 0.95
    lp: Optional[Any] = None
    distance = float("inf")
    for r in puts:
        st = float(_get(r, "strike", 0.0))
        if st < float(_get(short_put, "strike", 0.0)) and spot * 0.82 <= st <= spot * 0.97:
            d = abs(st - long_target)
            if d < distance:
                lp, distance = r, d
    if not lp:
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

    # Check OI and spreads
    sp1 = spread_pct(float(_get(short_put, "bid", 0.0)), float(_get(short_put, "ask", 0.0)))
    sp2 = spread_pct(float(_get(lp, "bid", 0.0)), float(_get(lp, "ask", 0.0)))
    per_leg_spread = None
    if sp1 is not None and sp2 is not None:
        per_leg_spread = max(sp1, sp2)
    oi_ok = int(_get(short_put, "oi", 0)) >= min_oi and int(_get(lp, "oi", 0)) >= min_oi
    spread_ok = per_leg_spread is not None and per_leg_spread <= max_spread

    credit = max(0.01, float(_get(short_put, "mid", (_get(short_put, "bid", 0.0) + _get(short_put, "ask", 0.0)) / 2)) - float(_get(lp, "mid", (_get(lp, "bid", 0.0) + _get(lp, "ask", 0.0)) / 2)))
    width = abs(float(_get(short_put, "strike", 0.0)) - float(_get(lp, "strike", 0.0)))
    credit_ok = credit >= credit_ratio * width

    return Structure(
        template="BullPutCredit",
        expiry=expiry,
        long_strike=float(_get(lp, "strike", 0.0)),
        short_strike=float(_get(short_put, "strike", 0.0)),
        debit_or_credit="credit",
        width=width,
        per_leg_oi_ok=bool(oi_ok),
        per_leg_spread_pct=per_leg_spread,
        needs_chain=not (oi_ok and spread_ok and credit_ok),
        limit_price=credit,
    )


def pick_structure(
    scan: ScanRow,
    chain: List[Any],
    direction: str,  # "long" | "short"
    cfg: Dict[str, object],
    tier: Optional[str] = None,
) -> Structure:
    expiry = _pick_expiry(chain)
    calls = _calls_by_strike([r for r in chain if hasattr(r, "right") or (isinstance(r, dict) and r.get("right"))])

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
            dc = Structure(
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
            # B-tier alternative: Bull Put Credit when DebitCall not available
            if tier == "B":
                return pick_bull_put_credit(scan.price, chain, expiry, cfg)
            return dc
        # find short strike at least min_width above
        short_strike = None
        for strike in sorted(calls):
            if strike >= long_call.strike + min_width:
                short_strike = strike
                break
        short_call = _call_at_strike(short_strike, calls) if short_strike else None
        if not short_call:
            dc = Structure(
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
            if tier == "B":
                return pick_bull_put_credit(scan.price, chain, expiry, cfg)
            return dc

        leg_spreads = [spread_pct(long_call.bid, long_call.ask), spread_pct(short_call.bid, short_call.ask)]
        # If any leg has no reliable spread, treat as failing spread check
        per_leg_spread = None
        if all(v is not None for v in leg_spreads):
            per_leg_spread = max([v for v in leg_spreads if v is not None])  # type: ignore[arg-type]
        oi_ok = long_call.oi >= min_oi and short_call.oi >= min_oi
        spread_ok = per_leg_spread is not None and per_leg_spread <= max_spread
        limit_price = max(0.01, long_call.mid - short_call.mid)
        dc_struct = Structure(
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
        if dc_struct.needs_chain and tier == "B":
            # Try Bull Put Credit as alternative when debit fails checks
            return pick_bull_put_credit(scan.price, chain, expiry, cfg)
        return dc_struct

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
