from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import List

try:
    from ib_insync import IB, Option, Future
except Exception:  # pragma: no cover - optional
    IB = Option = Future = None  # type: ignore

ib = IB() if IB else None
PORTFOLIO_FILES = ["tickers.txt"]


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _bs_delta(
    S: float, K: float, T: float, r: float, sigma: float, call: bool = True
) -> float:
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    return _norm_cdf(d1) if call else _norm_cdf(d1) - 1.0


def _parse_ib_month(text: str) -> datetime:
    try:
        if len(text) == 6:
            return datetime.strptime(text, "%Y%m")
        return datetime.strptime(text, "%Y%m%d")
    except Exception:
        return datetime(1900, 1, 1)


def _first_valid_expiry(
    symbol: str, expiries: List[str], strike: float, root: str
) -> str:
    for exp in expiries:
        tmpl = Option(symbol, exp, strike, "C") if Option else None
        cds = ib.reqContractDetails(tmpl) if ib else []
        if cds:
            return exp
    return expiries[0]


def front_future(symbol: str, exchange: str):
    tmpl = Future(symbol, exchange) if Future else None
    cds = ib.reqContractDetails(tmpl) if ib else []
    today = datetime.utcnow()
    for d in cds:
        dt = _parse_ib_month(d.contract.lastTradeDateOrContractMonth)
        if dt >= today:
            return d.contract
    return cds[0].contract if cds else tmpl


def load_tickers() -> List[str]:
    for path in PORTFOLIO_FILES:
        if Path(path).exists():
            return [
                line.strip()
                for line in Path(path).read_text().splitlines()
                if line.strip()
            ]
    raise SystemExit("Ticker file not found")
