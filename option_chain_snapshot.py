#!/usr/bin/env python3
"""
CLI wrapper for the option chain snapshot tool.

Examples:
  python option_chain_snapshot.py                 # interactive, CSV output
  python option_chain_snapshot.py --format excel  # interactive, Excel output
  python option_chain_snapshot.py --symbols MSFT,AAPL --format csv
  python option_chain_snapshot.py --symbol-expiries 'TSLA:20250620,20250703;AAPL:20250620'
"""

import argparse

from portfolio_exporter.scripts.option_chain_snapshot import run as run_snapshot


def main() -> None:
    p = argparse.ArgumentParser(description="Export option-chain snapshots")
    p.add_argument(
        "--symbols",
        type=str,
        help="Comma-separated tickers (overrides portfolio/files)",
    )
    p.add_argument(
        "--symbol-expiries",
        type=str,
        help=(
            "Semi-colon separated SYM:EXP list, e.g. 'TSLA:20250620,20250703;AAPL:20250620'"
        ),
    )
    fmt_grp = p.add_mutually_exclusive_group()
    fmt_grp.add_argument(
        "--format",
        choices=["csv", "excel", "pdf", "txt"],
        default="csv",
        help="Output format (default: csv)",
    )
    # Backwards-compatible toggles
    fmt_grp.add_argument("--excel", action="store_true", help="Save as Excel")
    fmt_grp.add_argument("--pdf", action="store_true", help="Save as PDF")
    fmt_grp.add_argument("--txt", action="store_true", help="Save as text")

    args = p.parse_args()

    fmt = args.format
    if args.excel:
        fmt = "excel"
    elif args.pdf:
        fmt = "pdf"
    elif args.txt:
        fmt = "txt"

    run_snapshot(fmt=fmt, symbols=args.symbols, symbol_expiries=args.symbol_expiries)


if __name__ == "__main__":
    main()

