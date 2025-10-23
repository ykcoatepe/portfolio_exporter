#!/usr/bin/env python3
"""Update tickers_live.txt from current IBKR portfolio."""

from __future__ import annotations
import os
from typing import List

try:
    from ib_insync import IB
except ImportError:  # pragma: no cover - optional dependency
    IB = None  # type: ignore

IB_HOST, IB_PORT, IB_CID = "127.0.0.1", 7496, 4  # dedicated clientId (set 7497 for paper)
PROXY_MAP = {"VIX": "^VIX", "VVIX": "^VVIX", "DXY": "DX-Y.NYB"}
TICKERS_FILE = "tickers_live.txt"


def fetch_ib_tickers() -> List[str]:
    """Return stock tickers from current IBKR positions."""
    if IB is None:
        return []
    ib = IB()
    try:
        ib.connect(IB_HOST, IB_PORT, clientId=IB_CID, timeout=3)
    except Exception:
        return []
    positions = ib.positions()
    ib.disconnect()
    tickers = {
        p.contract.symbol.upper()
        for p in positions
        if getattr(p.contract, "secType", "") == "STK"
    }
    return sorted(tickers)


def save_tickers(tickers: List[str], path: str = TICKERS_FILE) -> None:
    """Write tickers to a text file, one per line."""
    with open(path, "w") as fh:
        for tkr in tickers:
            mapped = PROXY_MAP.get(tkr, tkr)
            fh.write(f"{mapped}\n")


def main() -> None:
    tickers = fetch_ib_tickers()
    if not tickers:
        print("No tickers retrieved from IBKR.")
        return
    save_tickers(tickers)
    print(f"\u2705  Updated {TICKERS_FILE} with {len(tickers)} tickers.")


if __name__ == "__main__":
    main()
