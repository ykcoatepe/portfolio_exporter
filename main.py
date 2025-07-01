from __future__ import annotations

import argparse
from pathlib import Path

from src import analysis, data_fetching, reporting, interactive


def cmd_pulse(args: argparse.Namespace) -> None:
    tickers = args.tickers.split(",") if args.tickers else []
    ohlc = data_fetching.fetch_ohlc(tickers)
    df = analysis.compute_indicators(ohlc)
    out = Path(args.output)
    reporting.generate_report(df, str(out), fmt=args.format)


def cmd_live(args: argparse.Namespace) -> None:
    print("live feed not implemented in this demo")


def cmd_options(args: argparse.Namespace) -> None:
    print("options snapshot not implemented in this demo")


def cmd_report(args: argparse.Namespace) -> None:
    print("report not implemented in this demo")


def cmd_orchestrate(args: argparse.Namespace) -> None:
    print("dataset orchestration not implemented in this demo")


def main() -> None:
    parser = argparse.ArgumentParser(description="Portfolio exporter CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_pulse = sub.add_parser("pulse", help="Daily pulse report")
    p_pulse.add_argument("--tickers", help="Comma separated tickers", default="")
    p_pulse.add_argument("--output", default="pulse.csv")
    p_pulse.add_argument("--format", default="csv", choices=["csv", "excel", "pdf"])
    p_pulse.set_defaults(func=cmd_pulse)

    sub.add_parser("live", help="Live quotes").set_defaults(func=cmd_live)
    sub.add_parser("options", help="Option chains").set_defaults(func=cmd_options)
    sub.add_parser("report", help="Trades report").set_defaults(func=cmd_report)
    sub.add_parser("orchestrate", help="Dataset orchestration").set_defaults(
        func=cmd_orchestrate
    )

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
