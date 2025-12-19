#!/usr/bin/env python3
"""Update portfolio tickers (equities + option underlyings) from IBKR positions."""

from __future__ import annotations

from pathlib import Path

from portfolio_exporter.core.config import settings
from portfolio_exporter.core.ib_config import HOST as IB_HOST
from portfolio_exporter.core.ib_config import client_id as _cid
from portfolio_exporter.core.ib_config import connect_ib

try:
    from ib_insync import IB
except ImportError:  # pragma: no cover - optional dependency
    IB = None  # type: ignore

IB_CID = _cid("update_tickers", default=4)  # dedicated clientId
PROXY_MAP = {"VIX": "^VIX", "VVIX": "^VVIX", "DXY": "DX-Y.NYB"}
TICKERS_FILE = "tickers_live.txt"


def fetch_ib_symbols() -> tuple[list[str], list[str], int]:
    """Return equities, option underlyings, and option contract count."""
    if IB is None:
        return [], [], 0
    ib = IB()
    try:
        connect_ib(ib, host=IB_HOST, client_id=IB_CID, timeout=3)
    except Exception:
        return [], [], 0

    try:
        positions = ib.positions()
    except Exception:
        positions = []
    finally:
        try:
            ib.disconnect()
        except Exception:
            pass

    equities: set[str] = set()
    option_underlyings: set[str] = set()
    option_contracts = 0

    for pos in positions:
        contract = getattr(pos, "contract", None)
        if contract is None:
            continue
        sec_type = getattr(contract, "secType", "")
        symbol = getattr(contract, "symbol", "")
        if sec_type in {"STK", "ETF"} and symbol:
            equities.add(str(symbol).upper())
            continue
        if sec_type == "OPT":
            option_contracts += 1
            if symbol:
                option_underlyings.add(str(symbol).upper())
            continue
        if symbol and sec_type in {"FUT", "IND"}:
            equities.add(str(symbol).upper())

    return sorted(equities), sorted(option_underlyings), option_contracts


def fetch_ib_tickers() -> list[str]:
    """Backwards-compatible helper returning only equity tickers."""
    equities, _, _ = fetch_ib_symbols()
    return equities


def save_tickers(tickers: list[str], path: str = TICKERS_FILE) -> None:
    """Write tickers to a text file in the configured output directory."""
    outdir = Path(settings.output_dir).expanduser()
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
    equities, option_underlyings, option_contracts = fetch_ib_symbols()
    if not equities and not option_underlyings:
        print("No tickers retrieved from IBKR.")
        return

    combined: list[str] = []
    seen: set[str] = set()
    for symbol in equities + option_underlyings:
        if symbol not in seen:
            combined.append(symbol)
            seen.add(symbol)

    save_tickers(combined)

    outdir = Path(settings.output_dir).expanduser()
    parts: list[str] = []
    if equities:
        parts.append(f"{len(equities)} equities")
    if option_contracts:
        parts.append(f"{option_contracts} option contracts")
    summary = " and ".join(parts) if parts else "portfolio"

    print(f"\u2705  Synced {summary} from IBKR positions.")
    print(f"    Output → {outdir / TICKERS_FILE}")
