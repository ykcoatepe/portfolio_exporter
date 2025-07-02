from __future__ import annotations

import argparse
import sys
from pathlib import Path
import subprocess
import io
import os
import zipfile
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Tuple

import pandas as pd
from pypdf import PdfWriter
from fpdf import FPDF

from src import analysis, data_fetching, reporting, interactive
import logging
from src.data_fetching import get_portfolio_contracts


def get_timestamp() -> str:
    """Returns a formatted timestamp string for filenames."""
    return datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%Y%m%d_%H%M%S")


def cmd_pulse(args) -> None:
    tickers = args.tickers.split(",") if args.tickers else []
    ib = None  # Initialize ib to None
    try:
        if not tickers:
            print("Fetching portfolio contracts from IBKR for pulse report...")
            ib = data_fetching.IB()
            ib.connect(
                data_fetching.IB_HOST,
                data_fetching.IB_PORT,
                data_fetching.IB_CLIENT_ID,
                timeout=10,
            )

            contracts = data_fetching.get_portfolio_contracts(ib)
            if not contracts:
                print(
                    "No contracts found in IBKR portfolio. Please provide tickers manually or ensure IBKR is running and connected."
                )
                return

            # Extract underlying symbols from contracts
            underlying_symbols = set()
            for contract in contracts:
                if contract.secType == "OPT" or contract.secType == "BAG":
                    underlying_symbols.add(contract.symbol)
                else:  # For stocks, forex, etc.
                    underlying_symbols.add(contract.symbol)
            tickers = list(underlying_symbols)

        ohlc = data_fetching.fetch_ohlc(tickers)
        df = analysis.compute_indicators(ohlc)
        out = Path(OUTPUT_DIR) / args.output
        reporting.generate_report(df, str(out), fmt=args.format)
        print(f"Report generated to {out}")
    except ValueError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        if ib and ib.isConnected():
            ib.disconnect()


def cmd_live(args: argparse.Namespace) -> None:
    ib = data_fetching.IB()
    try:
        ib.connect(
            data_fetching.IB_HOST,
            data_fetching.IB_PORT,
            data_fetching.IB_CLIENT_ID,
            timeout=10,
        )
        logging.basicConfig(level=logging.DEBUG)

        print("Fetching portfolio contracts from IBKR...")
        contracts = data_fetching.get_portfolio_contracts(ib)

        if not contracts:
            print("No contracts found in IBKR portfolio.")
            return

        ib_quotes = data_fetching.fetch_ib_quotes(ib, contracts)

        # Fallback to Yahoo Finance for tickers that failed in IBKR
        ib_tickers = ib_quotes["ticker"].unique() if not ib_quotes.empty else []

        all_symbols = []
        for c in contracts:
            if c.secType == "BAG":
                all_symbols.append(data_fetching._format_combo_symbol(c))
            else:
                all_symbols.append(c.symbol)

        missing_tickers = [t for t in all_symbols if t not in ib_tickers]

        if missing_tickers:
            print(f"Fetching missing tickers from Yahoo Finance: {missing_tickers}")
            yf_quotes = data_fetching.fetch_yf_quotes(missing_tickers)
        else:
            yf_quotes = pd.DataFrame()

        if not ib_quotes.empty and not yf_quotes.empty:
            quotes = pd.concat([ib_quotes, yf_quotes]).drop_duplicates(
                subset=["ticker", "source"]
            )
        elif not ib_quotes.empty:
            quotes = ib_quotes
        elif not yf_quotes.empty:
            quotes = yf_quotes
        else:
            print("No live quotes fetched.")
            return

        out = Path(OUTPUT_DIR) / args.output
        quotes.to_csv(out, index=False)
        print(f"Live quotes saved to {out}")

    except Exception as e:
        print(f"Error fetching live quotes: {e}")
    finally:
        if ib.isConnected():
            ib.disconnect()


def cmd_options(args: argparse.Namespace) -> None:
    try:
        ib = data_fetching.IB()
        ib.connect(
            data_fetching.IB_HOST,
            data_fetching.IB_PORT,
            data_fetching.IB_CLIENT_ID,
            timeout=10,
        )
        df = data_fetching.snapshot_chain(ib, args.symbol, args.expiry_hint)
        if not df.empty:
            out_path = Path(OUTPUT_DIR) / f"{args.symbol}_options_{get_timestamp()}.csv"
            df.to_csv(out_path, index=False)
            print(f"Option chain saved to {out_path}")
        else:
            print(f"No option chain data found for {args.symbol}")
        ib.disconnect()
    except Exception as e:
        print(f"Error fetching option chain: {e}")


def cmd_positions(args: argparse.Namespace) -> None:
    try:
        df = data_fetching.load_ib_positions_ib(group_by_combo=args.group_by_combo)
        if not df.empty:
            out_path = Path(OUTPUT_DIR) / args.output
            df.to_csv(out_path, index=False)
            print(f"Positions report saved to {out_path}")
        else:
            print("No positions found.")
    except Exception as e:
        print(f"Error fetching positions: {e}")


def cmd_report(args: argparse.Namespace) -> None:
    try:
        trades_df = pd.read_csv(args.input)
        formatted_trades = reporting.format_trades(trades_df.to_dict(orient="records"))
        reporting.generate_report(
            formatted_trades, str(Path(OUTPUT_DIR) / args.output), fmt=args.format
        )
        print(f"Trades report generated to {args.output}")
    except FileNotFoundError:
        print(f"Error: Input file not found at {args.input}")
    except Exception as e:
        print(f"An error occurred while generating the trades report: {e}")


def cmd_portfolio_greeks(args: argparse.Namespace) -> None:
    try:
        ib = data_fetching.IB()
        ib.connect(
            data_fetching.IB_HOST,
            data_fetching.IB_PORT,
            data_fetching.IB_CLIENT_ID,
            timeout=args.ib_timeout,
        )
        bundles = data_fetching.list_positions(ib)
        rows = []
        for pos, tk in bundles:
            g = getattr(tk, "modelGreeks", None)
            if not g:
                continue
            rows.append(
                {
                    "underlying": pos.contract.symbol,
                    "position": pos.position,
                    "multiplier": getattr(pos.contract, "multiplier", 1),
                    "delta": g.delta,
                    "gamma": g.gamma,
                    "vega": g.vega,
                    "theta": g.theta,
                    "rho": g.optRho,
                }
            )
        ib.disconnect()
        df = pd.DataFrame(rows)
        greeks = analysis.calc_portfolio_greeks(df, None)
        out_path = Path(OUTPUT_DIR) / f"portfolio_greeks_{get_timestamp()}.csv"
        greeks.to_csv(out_path, index=True)
        print(f"Greeks saved to {out_path}")
    except Exception as e:
        print(f"Error calculating portfolio greeks: {e}")


OUTPUT_DIR = (
    "/Users/yordamkocatepe/Library/Mobile Documents/com~apple~CloudDocs/Downloads"
)
os.makedirs(OUTPUT_DIR, exist_ok=True)


def run_script(cmd: list[str]) -> List[str]:
    """Run a script and return the newly created files in OUTPUT_DIR."""
    out_dir = OUTPUT_DIR
    before = set(os.listdir(out_dir))
    env = os.environ.copy()
    env["OUTPUT_DIR"] = out_dir
    subprocess.run(
        [sys.executable, *cmd],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=600,  # fail fast if a script hangs >10 min
        env=env,
    )
    after = set(os.listdir(out_dir))
    new = after - before
    return [os.path.join(out_dir, f) for f in new]


def merge_pdfs(files_by_script: List[Tuple[str, List[str]]], dest: str) -> None:
    """Merge the given PDF files into a single output, adding bookmarks for each script and title pages, skipping non-PDF files."""
    merger = PdfWriter()
    for title, files in files_by_script:
        pdfs = [path for path in files if path.lower().endswith(".pdf")]
        if not pdfs:
            continue

        clean_title = title.replace("_", " ").replace(".py", "").title()

        # Create a title page using FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 24)
        pdf.cell(0, 100, clean_title, 0, 1, "C")

        # Save the title page to a BytesIO object
        title_page_pdf = io.BytesIO(pdf.output(dest="S").encode("latin-1"))
        merger.append(title_page_pdf)

        # Add bookmark for the title page
        merger.add_outline_item(clean_title, len(merger.pages) - 1)

        for path in pdfs:
            merger.append(path)
    merger.write(dest)
    merger.close()


def create_zip(files: List[str], dest: str) -> None:
    """Create a zip archive containing the given files."""
    with zipfile.ZipFile(dest, "w") as zf:
        for path in files:
            zf.write(path, os.path.basename(path))


def cleanup(files: List[str]) -> None:
    """Delete the given files, ignoring missing paths."""
    for path in files:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def cmd_orchestrate(args: argparse.Namespace) -> None:
    try:
        ts = get_timestamp()

        scripts = [
            ["main.py", "pulse", "--output", f"pulse_{get_timestamp()}.csv"],
            [
                "main.py",
                "live",
                "--tickers",
                "SPY,QQQ",
                "--output",
                f"live_quotes_{get_timestamp()}.csv",
            ],
            [
                "main.py",
                "options",
                "--symbol",
                "SPY",
                "--output",
                f"options_{get_timestamp()}.csv",
            ],
        ]
        # Add format flag if not default
        if args.format == "pdf":
            for script in scripts:
                script.append("--format")
                script.append("pdf")

        files_by_script: List[Tuple[str, List[str]]] = []
        for cmd in scripts:
            new_files = run_script(cmd)
            if new_files:
                files_by_script.append((cmd[1], new_files))

        all_files = [f for _, file_list in files_by_script for f in file_list]
        if args.format == "pdf":
            dest = os.path.join(OUTPUT_DIR, f"dataset_{get_timestamp()}.pdf")
            merge_pdfs(files_by_script, dest)
        else:
            dest = os.path.join(OUTPUT_DIR, f"dataset_{get_timestamp()}.zip")
            create_zip(all_files, dest)

        cleanup(all_files)
        print(f"Created {dest}")
    except Exception as e:
        print(f"An error occurred during orchestration: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Portfolio Exporter CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Pulse command
    pulse_parser = subparsers.add_parser("pulse", help="Generate a daily pulse report")
    pulse_parser.add_argument(
        "--tickers", type=str, help="Comma-separated list of tickers"
    )
    pulse_parser.add_argument(
        "--output",
        type=str,
        default=f"pulse_{get_timestamp()}.csv",
        help="Output file name",
    )
    pulse_parser.add_argument(
        "--format",
        type=str,
        default="csv",
        choices=["csv", "excel", "pdf"],
        help="Output format",
    )

    # Live command
    live_parser = subparsers.add_parser("live", help="Fetch live quotes")
    live_parser.add_argument(
        "--tickers", type=str, help="Comma-separated list of tickers"
    )
    live_parser.add_argument(
        "--output",
        type=str,
        default=f"live_quotes_{get_timestamp()}.csv",
        help="Output file name",
    )
    live_parser.add_argument(
        "--format",
        type=str,
        default="csv",
        choices=["csv", "excel", "pdf", "txt"],
        help="Output format",
    )

    # Options command
    options_parser = subparsers.add_parser(
        "options", help="Fetch option chain snapshot"
    )
    options_parser.add_argument(
        "--symbol", type=str, required=True, help="Stock symbol for option chain"
    )
    options_parser.add_argument(
        "--expiry-hint",
        type=str,
        help="Expiry hint (e.g., YYYYMMDD, YYYYMM, month name)",
    )
    options_parser.add_argument(
        "--format",
        type=str,
        default="csv",
        choices=["csv", "excel", "pdf", "txt"],
        help="Output format",
    )

    # Positions command
    positions_parser = subparsers.add_parser(
        "positions", help="Fetch portfolio positions"
    )
    positions_parser.add_argument(
        "--group-by-combo", action="store_true", help="Group positions by combo"
    )
    positions_parser.add_argument(
        "--output",
        type=str,
        default=f"positions_{get_timestamp()}.csv",
        help="Output file name",
    )
    positions_parser.add_argument(
        "--format",
        type=str,
        default="csv",
        choices=["csv", "excel", "pdf", "txt"],
        help="Output format",
    )

    # Report command
    report_parser = subparsers.add_parser("report", help="Generate a trades report")
    report_parser.add_argument(
        "--input", type=str, required=True, help="Path to trades CSV file"
    )
    report_parser.add_argument(
        "--output",
        type=str,
        default=f"trades_report_{get_timestamp()}.csv",
        help="Output file name",
    )
    report_parser.add_argument(
        "--format",
        type=str,
        default="csv",
        choices=["csv", "excel", "pdf"],
        help="Output format",
    )

    # Orchestrate command
    orchestrate_parser = subparsers.add_parser(
        "orchestrate", help="Run a sequence of commands"
    )
    orchestrate_parser.add_argument(
        "--format",
        type=str,
        default="csv",
        choices=["csv", "pdf"],
        help="Output format for the dataset",
    )

    # Portfolio Greeks command
    greeks_parser = subparsers.add_parser(
        "portfolio-greeks", help="Calculate portfolio Greeks"
    )
    greeks_parser.add_argument(
        "--ib-timeout", type=float, default=10.0, help="IBKR timeout seconds"
    )
    greeks_parser.add_argument(
        "--format",
        type=str,
        default="csv",
        choices=["csv", "excel", "pdf", "txt"],
        help="Output format",
    )

    # Check if any command-line arguments were provided
    if len(sys.argv) > 1:
        args = parser.parse_args()
        if args.command == "pulse":
            cmd_pulse(args)
        elif args.command == "live":
            cmd_live(args)
        elif args.command == "options":
            cmd_options(args)
        elif args.command == "positions":
            cmd_positions(args)
        elif args.command == "report":
            cmd_report(args)
        elif args.command == "orchestrate":
            cmd_orchestrate(args)
        elif args.command == "portfolio-greeks":
            cmd_portfolio_greeks(args)
    else:
        # Interactive mode
        while True:
            print("\nSelect a command:")
            print("1. pulse (Daily pulse report)")
            print("2. live (Live quotes)")
            print("3. options (Option chains)")
            print("4. positions (Portfolio positions)")
            print("5. report (Trades report)")
            print("6. portfolio-greeks (Greeks summary)")
            print("7. orchestrate (Dataset orchestration)")
            print("8. Exit")

            choice = input("Enter your choice (1-7): ")

            if choice == "1":
                tickers = input(
                    "Enter tickers (comma-separated, e.g., AAPL,MSFT; leave blank to fetch from IBKR): "
                )
                output = (
                    input(
                        f"Enter output file name (default: pulse_{get_timestamp()}.csv): "
                    )
                    or f"pulse_{get_timestamp()}.csv"
                )
                fmt = (
                    input("Enter output format (csv, excel, pdf; default: csv): ")
                    or "csv"
                )

                class Args:
                    pass

                args = Args()
                args.tickers = tickers
                args.output = output
                args.format = fmt
                cmd_pulse(args)
            elif choice == "2":
                tickers = input("Enter tickers (comma-separated, e.g., AAPL,MSFT): ")
                output = (
                    input(
                        f"Enter output file name (default: live_quotes_{get_timestamp()}.csv): "
                    )
                    or f"live_quotes_{get_timestamp()}.csv"
                )

                class Args:
                    pass

                args = Args()
                args.tickers = tickers
                args.output = output
                cmd_live(args)
            elif choice == "3":
                symbol = input("Enter stock symbol for option chain (e.g., SPY): ")
                expiry_hint = input(
                    "Enter expiry hint (optional, e.g., YYYYMMDD, YYYYMM, month name): "
                )

                class Args:
                    pass

                args = Args()
                args.symbol = symbol
                args.expiry_hint = expiry_hint if expiry_hint else None
                cmd_options(args)
            elif choice == "4":
                group_by_combo = input("Group by combo? (y/n): ").lower() == "y"
                output = (
                    input(
                        f"Enter output file name (default: positions_{get_timestamp()}.csv): "
                    )
                    or f"positions_{get_timestamp()}.csv"
                )

                class Args:
                    pass

                args = Args()
                args.group_by_combo = group_by_combo
                args.output = output
                cmd_positions(args)
            elif choice == "5":
                input_file = input("Enter path to trades CSV file: ")
                output = (
                    input(
                        f"Enter output file name (default: trades_report_{get_timestamp()}.csv): "
                    )
                    or f"trades_report_{get_timestamp()}.csv"
                )
                fmt = (
                    input("Enter output format (csv, excel, pdf; default: csv): ")
                    or "csv"
                )

                class Args:
                    pass

                args = Args()
                args.input = input_file
                args.output = output
                args.format = fmt
                cmd_report(args)
            elif choice == "6":

                class Args:
                    pass

                args = Args()
                args.ib_timeout = 10.0
                cmd_portfolio_greeks(args)
            elif choice == "7":
                fmt = input("Enter output format (csv, pdf; default: csv): ") or "csv"

                class Args:
                    pass

                args = Args()
                args.format = fmt
                cmd_orchestrate(args)
            elif choice == "8":
                print("Exiting.")
                break
            else:
                print("Invalid choice. Please try again.")


if __name__ == "__main__":
    main()
