#!/usr/bin/env python3
"""Update tickers_live.txt from current IBKR portfolio."""

from __future__ import annotations

from pathlib import Path

from portfolio_exporter.core.config import settings
from portfolio_exporter.core.ib_config import HOST as IB_HOST
from portfolio_exporter.core.ib_config import PORT as IB_PORT
from portfolio_exporter.core.ib_config import client_id as _cid

try:
    from ib_insync import IB
except ImportError:  # pragma: no cover - optional dependency
    IB = None  # type: ignore

IB_CID = _cid("update_tickers", default=4)  # dedicated clientId
PROXY_MAP = {"VIX": "^VIX", "VVIX": "^VVIX", "DXY": "DX-Y.NYB"}
TICKERS_FILE = "tickers_live.txt"


def fetch_ib_tickers() -> list[str]:
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
    tickers = {p.contract.symbol.upper() for p in positions if getattr(p.contract, "secType", "") == "STK"}
    return sorted(tickers)


def save_tickers(tickers: list[str], path: str = TICKERS_FILE) -> None:
    """Write tickers to a text file in the configured output directory.

    If a relative path is provided, it is resolved under ``settings.output_dir``.
    Absolute paths are respected but their parent directories will be created.
    """
    outdir = Path(settings.output_dir).expanduser()
    # Resolve relative paths under the configured output directory
    target = Path(path)
    if not target.is_absolute():
        target = outdir / target
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w") as fh:
        for tkr in tickers:
            mapped = PROXY_MAP.get(tkr, tkr)
            fh.write(f"{mapped}\n")


def run(fmt: str = "csv") -> None:
    """Update ticker list from IBKR positions."""
    tickers = fetch_ib_tickers()
    if not tickers:
        print("No tickers retrieved from IBKR.")
        return
    save_tickers(tickers)
    print(f"\u2705  Updated {TICKERS_FILE} with {len(tickers)} tickers in output dir.")
