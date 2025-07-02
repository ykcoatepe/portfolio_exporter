from __future__ import annotations

import os
from typing import List

try:
    from ib_insync import IB
except Exception:  # pragma: no cover - optional
    IB = None  # type: ignore

PROXY_MAP = {"VIX": "^VIX"}


def save_tickers(tickers: List[str], path: str) -> None:
    """Write tickers to ``path`` applying ``PROXY_MAP``."""
    mapped = [PROXY_MAP.get(t, t) for t in tickers]
    with open(path, "w") as f:
        f.write("\n".join(mapped))


def fetch_ib_tickers(
    host: str = "127.0.0.1", port: int = 7497, client_id: int = 10
) -> List[str]:
    """Return stock tickers from the IBKR portfolio."""
    if IB is None:
        return []
    ib = IB()
    ib.connect(host, port, clientId=client_id, timeout=3)
    positions = ib.positions()
    ib.disconnect()
    tickers = [p.contract.symbol for p in positions if p.contract.secType == "STK"]
    return sorted(set(tickers))
