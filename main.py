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

from rich.console import Console

console = Console(stderr=True)


def get_timestamp() -> str:
    """Returns a formatted timestamp string for filenames."""
    return datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%Y%m%d_%H%M%S")


def cmd_pulse(args) -> None:
    tickers = args.tickers.split(",") if args.tickers else []
    ib = None
    try:
        if not tickers:
            console.print("[bold cyan]Fetching portfolio contracts from IBKR for pulse report...[/]")
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

        console.print(f"[bold cyan]Fetching historical prices for {len(tickers)} tickers...[/]")
        ohlc = data_fetching.fetch_ohlc(tickers)
        console.print("[bold cyan]Computing technical indicators...[/]")
        df = analysis.compute_indicators(ohlc)
        out = Path(OUTPUT_DIR) / args.output
        console.print(f"[bold cyan]Generating {args.format.upper()} report...[/]")
        reporting.generate_report(df, str(out), fmt=args.format)
        console.print(f"[bold green]Report generated to {out}[/]")
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
        console.print("[bold cyan]Connecting to IBKR for live quotes...[/]")
        ib.connect(
            data_fetching.IB_HOST,
            data_fetching.IB_PORT,
            data_fetching.IB_CLIENT_ID,
            timeout=10,
        )
        logging.basicConfig(level=logging.DEBUG)

        console.print("[bold cyan]Fetching portfolio contracts from IBKR...[/]")
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
            console.print(f"[bold cyan]Fetching missing tickers from Yahoo Finance: {missing_tickers}[/]")
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
        console.print(f"[bold green]Live quotes saved to {out}[/]")

    except Exception as e:
        print(f"Error fetching live quotes: {e}")
    finally:
        if ib.isConnected():
            ib.disconnect()


def cmd_options(args: argparse.Namespace) -> None:
    try:
        console.print("[bold cyan]Connecting to IBKR for option chain...[/]")
        ib = data_fetching.IB()
        ib.connect(
            data_fetching.IB_HOST,
            data_fetching.IB_PORT,
            data_fetching.IB_CLIENT_ID,
            timeout=10,
        )

        tickers: list[str] = []
        if getattr(args, "tickers", None):
            tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
        elif getattr(args, "symbol", None):
            tickers = [args.symbol.upper()]
        else:
            tickers = [input("Enter stock symbol: ").strip().upper()]

        expiries: list[str | None] = []
        if getattr(args, "expiries", None):
            expiries = [e.strip() for e in args.expiries.split(",") if e.strip()]
        elif getattr(args, "expiry_hint", None):
            expiries = [args.expiry_hint]

        for sym in tickers:
            for exp in (expiries or [None]):
                console.print(f"[bold cyan]Fetching option chain for {sym} (expiry: {exp or 'auto'})...[/]")
                df = data_fetching.snapshot_chain(ib, sym, exp)
                if not df.empty:
                    exp_part = exp or "auto"
                    out_file = (
                        args.output
                        if args.output and len(tickers) == 1 and len(expiries or []) == 1
                        else f"{sym}_{exp_part}_options_{get_timestamp()}.csv"
                    )
                    out_path = Path(OUTPUT_DIR) / out_file
                    df.to_csv(out_path, index=False)
                    console.print(f"[bold green]Option chain saved to {out_path}[/]")
                else:
                    console.print(f"[bold yellow]No option chain data found for {sym}[/]")
        ib.disconnect()
    except Exception as e:
        print(f"Error fetching option chain: {e}")


def cmd_positions(args: argparse.Namespace) -> None:
    try:
        console.print("[bold cyan]Fetching portfolio positions from IBKR...[/]")
        df = data_fetching.load_ib_positions_ib(group_by_combo=args.group_by_combo)
        if not df.empty:
            out_path = Path(OUTPUT_DIR) / args.output
            df.to_csv(out_path, index=False)
            console.print(f"[bold green]Positions report saved to {out_path}[/]")
        else:
            console.print("[bold yellow]No positions found.[/]")
    except Exception as e:
        console.print(f"[bold red]Error fetching positions: {e}[/]")


def cmd_report(args: argparse.Namespace) -> None:
    try:
        console.print(f"[bold cyan]Reading trades from {args.input}...[/]")
        trades_df = pd.read_csv(args.input)
        out_path = Path(OUTPUT_DIR) / args.output
        console.print(f"[bold cyan]Saving trades report to {out_path}...[/]")
        trades_df.to_csv(out_path, index=False)
        console.print(f"[bold green]Trades report saved to {out_path}[/]")
    except FileNotFoundError:
        console.print(f"[bold red]Error: Input file not found at {args.input}[/]")
    except Exception as e:
        console.print(f"[bold red]An error occurred while generating the trades report: {e}[/]")


def cmd_portfolio_greeks(args: argparse.Namespace) -> None:
    try:
        console.print("[bold cyan]Connecting to IBKR and fetching option positions for Greeks...[/]")
        ib = data_fetching.IB()
        ib.connect(
            data_fetching.IB_HOST,
            data_fetching.IB_PORT,
            data_fetching.IB_CLIENT_ID,
            timeout=args.ib_timeout,
        )
        bundles = data_fetching.list_positions(ib)
        print(f"DEBUG: Bundles: {bundles}")
        rows = []
        for pos, tk in bundles:
            g = getattr(tk, "modelGreeks", None)
            if not g:
                print(f"DEBUG: No greeks for {pos.contract.symbol}")
                continue
            rows.append(
                {
                    "underlying": pos.contract.symbol,
                    "position": pos.position,
                    "multiplier": getattr(pos.contract, "multiplier", 1),
                    "delta": getattr(g, "delta", 0.0),
                    "gamma": getattr(g, "gamma", 0.0),
                    "vega": getattr(g, "vega", 0.0),
                    "theta": getattr(g, "theta", 0.0),
                    "rho": getattr(g, "rho", 0.0),
                }
            )
        ib.disconnect()
        print(f"DEBUG: Rows before DataFrame: {rows}")
        console.print("[bold cyan]Calculating portfolio Greeks exposures...[/]")
        df = pd.DataFrame(rows)
        print(f"DEBUG: DataFrame after creation: {df.head()}")
        if df.empty:
            print("DEBUG: DataFrame is empty, skipping further processing.")
            return
        console.print("[bold cyan]Loading portfolio holdings for index filtering...[/]")
        holdings = data_fetching.load_ib_positions_ib()
        print(f"DEBUG: Holdings: {holdings.head()}")
        greeks = analysis.calc_portfolio_greeks(
            df, holdings, include_indices=args.include_indices
        )
        print(f"DEBUG: Greeks DataFrame after calc: {greeks.head()}")
        if greeks.empty:
            print("DEBUG: Greeks DataFrame is empty, skipping CSV generation.")
            return
        out_path = Path(OUTPUT_DIR) / f"portfolio_greeks_{get_timestamp()}.csv"
        
        greeks.to_csv(out_path, index=True)
        console.print(f"[bold green]Greeks saved to {out_path}[/]")
        print(f"DEBUG: Greeks saved to {out_path}")
        console.print(f"[bold yellow]Greeks DataFrame head before saving:\n{greeks.head()}[/]")
        console.print(f"[bold yellow]Greeks DataFrame head before saving:\n{greeks.head()}[/]")
    except Exception as e:
        console.print(f"[bold red]Error calculating portfolio greeks: {e}[/]")


DEFAULT_OUTPUT_DIR = Path("/Users/yordamkocatepe/Library/Mobile Documents/com~apple~CloudDocs/Downloads")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR))
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
        stdout=sys.stdout,
        stderr=sys.stderr,
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
        console.print("[bold cyan]Running dataset orchestration (pulse, live, options)...[/]")
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
            console.print(f"[bold cyan]Merging PDFs into {dest}...[/]")
            merge_pdfs(files_by_script, dest)
        else:
            dest = os.path.join(OUTPUT_DIR, f"dataset_{get_timestamp()}.zip")
            console.print(f"[bold cyan]Creating ZIP archive {dest}...[/]")
            create_zip(all_files, dest)

        cleanup(all_files)
        console.print(f"[bold green]Orchestration complete! Dataset at {dest}[/]")
    except Exception as e:
        console.print(f"[bold red]An error occurred during orchestration: {e}[/]")


def main() -> None:
    global OUTPUT_DIR
    parser = argparse.ArgumentParser(description="Portfolio Exporter CLI")
    parser.add_argument(
        "--output-dir",
        type=str,
        default=OUTPUT_DIR,
        help="Directory to write output files",
    )
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
        "--tickers", type=str, help="Comma-separated stock symbols"
    )
    options_parser.add_argument("--symbol", type=str, help=argparse.SUPPRESS)
    options_parser.add_argument(
        "--expiries", type=str, help="Comma-separated expiry hints"
    )
    options_parser.add_argument("--expiry-hint", type=str, help=argparse.SUPPRESS)
    options_parser.add_argument("--output", type=str, help="Output file name")
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
    greeks_parser.add_argument(
        "--include-indices",
        action="store_true",
        help="Include index underlyings (VIX, SPX) in the report",
    )

    # Check if any command-line arguments were provided
    if len(sys.argv) > 1:
        args = parser.parse_args()
        OUTPUT_DIR = args.output_dir
        os.makedirs(OUTPUT_DIR, exist_ok=True)
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

            choice = input("Enter your choice (1-8): ").strip()

            try:
                choice_num = int(choice)
            except ValueError:
                print("Invalid choice. Please enter a number between 1 and 8.")
                continue

            if choice_num == 8:
                print("Exiting.")
                break

            commands = {
                1: cmd_pulse,
                2: cmd_live,
                3: cmd_options,
                4: cmd_positions,
                5: cmd_report,
                6: cmd_portfolio_greeks,
                7: cmd_orchestrate,
            }

            if choice_num in commands:
                # Prepare args based on the command
                args = argparse.Namespace()
                if choice_num == 1:  # pulse
                    args.tickers = input(
                        "Enter tickers (comma-separated, e.g., AAPL,MSFT; leave blank to fetch from IBKR): "
                    ).strip()
                    args.output = (
                        input(
                            f"Enter output file name (default: pulse_{get_timestamp()}.csv): "
                        ).strip()
                        or f"pulse_{get_timestamp()}.csv"
                    )
                    args.format = (
                        input(
                            "Enter output format (csv, excel, pdf; default: csv): "
                        ).strip()
                        or "csv"
                    )
                elif choice_num == 2:  # live
                    args.tickers = input(
                        "Enter tickers (comma-separated, e.g., AAPL,MSFT): "
                    ).strip()
                    args.output = (
                        input(
                            f"Enter output file name (default: live_quotes_{get_timestamp()}.csv): "
                        ).strip()
                        or f"live_quotes_{get_timestamp()}.csv"
                    )
                    args.format = "csv"  # Default for live, as per original code
                elif choice_num == 3:  # options
                    args.symbol = input(
                        "Enter stock symbol for option chain (e.g., SPY): "
                    ).strip()
                    args.expiry_hint = (
                        input(
                            "Enter expiry hint (optional, e.g., YYYYMMDD, YYYYMM, month name): "
                        ).strip()
                        or None
                    )
                    args.format = "csv"  # Default for options, as per original code
                elif choice_num == 4:  # positions
                    args.group_by_combo = (
                        input("Group by combo? (y/n): ").lower().strip() == "y"
                    )
                    args.output = (
                        input(
                            f"Enter output file name (default: positions_{get_timestamp()}.csv): "
                        ).strip()
                        or f"positions_{get_timestamp()}.csv"
                    )
                    args.format = "csv"  # Default for positions, as per original code
                elif choice_num == 5:  # report
                    args.input = input("Enter path to trades CSV file: ").strip()
                    args.output = (
                        input(
                            f"Enter output file name (default: trades_report_{get_timestamp()}.csv): "
                        ).strip()
                        or f"trades_report_{get_timestamp()}.csv"
                    )
                    args.format = (
                        input(
                            "Enter output format (csv, excel, pdf; default: csv): "
                        ).strip()
                        or "csv"
                    )
                elif choice_num == 6:  # portfolio-greeks
                    args.ib_timeout = 10.0
                    args.format = "csv"
                    include = input("Include index underlyings (VIX, SPX)? (y/n): ").lower().strip() == "y"
                    args.include_indices = include
                    args.output = f"portfolio_greeks_{get_timestamp()}.csv"
                elif choice_num == 7:  # orchestrate
                    args.format = (
                        input("Enter output format (csv, pdf; default: csv): ").strip()
                        or "csv"
                    )
                    # Orchestrate doesn't use these directly, but for consistency with other commands
                    args.tickers = ""
                    args.output = ""

                commands[choice_num](args)
            else:
                print("Invalid choice. Please try again.")


if __name__ == "__main__":
    main()
