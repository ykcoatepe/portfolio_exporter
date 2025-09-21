from __future__ import annotations

import datetime as _dt
import re
from typing import NamedTuple

import dateparser


class Leg(NamedTuple):
    right: str  # "C" or "P"
    strike: float
    expiry: _dt.date


class ParsedOrder(NamedTuple):
    underlying: str
    legs: list[Leg]  # one or two legs supported for now
    qty: int  # default 1


_STRIKE_RGX = re.compile(r"(?P<k1>\d+(?:\.\d+)?)(?:/|‑)?(?P<k2>\d+(?:\.\d+)?)?" r"(?P<right>[CPcp])?$")

LAST_PARSED: ParsedOrder | None = None


def parse_order_line(text: str) -> ParsedOrder | None:
    """
    Parse shorthand like:
        'SPY 620/630C 18‑Oct‑25'
        'spy 430p nov15 x3'
        'QQQ 350c +45d'
    Returns ParsedOrder or None if unparseable.
    Rules:
        • first token = symbol
        • next token = strike or strike/strike + right
        • next = expiry (natural‑lang parsed via dateparser)
        • optional 'xN' for quantity
    """
    if not text.strip():
        return None
    toks = text.upper().split()
    if len(toks) < 2:
        return None
    sym = toks[0]
    qty = 1
    if "X" in toks[-1]:
        try:
            qty = int(toks[-1].lstrip("X"))
            toks = toks[:-1]
        except ValueError:
            pass
    m = _STRIKE_RGX.match(toks[1])
    if not m:
        return None
    k1, k2 = m.group("k1"), m.group("k2")
    right = (m.group("right") or "C").upper()
    strikes = [float(k1)]
    if k2:
        strikes.append(float(k2))
    expiry_txt = " ".join(toks[2:]) if len(toks) > 2 else "+30d"
    exp_dt = dateparser.parse(expiry_txt, settings={"PREFER_DATES_FROM": "future"})
    if not exp_dt:
        return None
    exp_dt = exp_dt.date()
    legs = [Leg(right=right, strike=s, expiry=exp_dt) for s in strikes]
    parsed = ParsedOrder(underlying=sym, legs=legs, qty=qty)
    global LAST_PARSED
    LAST_PARSED = parsed
    return parsed
