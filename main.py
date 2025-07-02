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

from pypdf import PdfWriter
from fpdf import FPDF

from src import analysis, data_fetching, reporting, interactive
from src.data_fetching import get_portfolio_tickers_from_ib

def get_timestamp() -> str:
    """Returns a formatted timestamp string for filenames."""
    return datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%Y%m%d_%H%M%S")


def cmd_pulse(args) -> None:
    tickers = args.tickers.split(",") if args.tickers else []
    if not tickers:
        print("Fetching portfolio tickers from IBKR...")
        tickers = get_portfolio_tickers_from_ib()
        if not tickers:
            print("No tickers found in IBKR portfolio. Please provide tickers manually or ensure IBKR is running and connected.")
            return
    try:
        ohlc = data_fetching.fetch_ohlc(tickers)
        df = analysis.compute_indicators(ohlc)
        out = Path(OUTPUT_DIR) / args.output
        reporting.generate_report(df, str(out), fmt=args.format)
    except ValueError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


def cmd_live(args: argparse.Namespace) -> None:
    tickers = args.tickers.split(",") if args.tickers else []
    if not tickers:
        print("Please provide tickers for live feed.")
        return
    try:
        ib_quotes = data_fetching.fetch_ib_quotes(tickers, [])
        yf_quotes = data_fetching.fetch_yf_quotes(tickers)
        
        if not ib_quotes.empty and not yf_quotes.empty:
            quotes = pd.concat([ib_quotes, yf_quotes]).drop_duplicates(subset=['ticker', 'source'])
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


def cmd_options(args: argparse.Namespace) -> None:
    try:
        ib = data_fetching.IB()
        ib.connect(data_fetching.IB_HOST, data_fetching.IB_PORT, data_fetching.IB_CLIENT_ID, timeout=10)
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


def cmd_report(args: argparse.Namespace) -> None:
    try:
        trades_df = pd.read_csv(args.input)
        formatted_trades = reporting.format_trades(trades_df.to_dict(orient='records'))
        reporting.generate_report(formatted_trades, str(Path(OUTPUT_DIR) / args.output), fmt=args.format)
        print(f"Trades report generated to {args.output}")
    except FileNotFoundError:
        print(f"Error: Input file not found at {args.input}")
    except Exception as e:
        print(f"An error occurred while generating the trades report: {e}")



OUTPUT_DIR = "/Users/yordamkocatepe/Library/Mobile Documents/com~apple~CloudDocs/Downloads"
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
            ["main.py", "live", "--tickers", "SPY,QQQ", "--output", f"live_quotes_{get_timestamp()}.csv"],
            ["main.py", "options", "--symbol", "SPY", "--output", f"options_{get_timestamp()}.csv"],
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
    pulse_parser.add_argument("--tickers", type=str, help="Comma-separated list of tickers")
    pulse_parser.add_argument("--output", type=str, default=f"pulse_{get_timestamp()}.csv", help="Output file name")
    pulse_parser.add_argument("--format", type=str, default="csv", choices=["csv", "excel", "pdf"], help="Output format")

    # Live command
    live_parser = subparsers.add_parser("live", help="Fetch live quotes")
    live_parser.add_argument("--tickers", type=str, help="Comma-separated list of tickers")
    live_parser.add_argument("--output", type=str, default=f"live_quotes_{get_timestamp()}.csv", help="Output file name")

    # Options command
    options_parser = subparsers.add_parser("options", help="Fetch option chain snapshot")
    options_parser.add_argument("--symbol", type=str, required=True, help="Stock symbol for option chain")
    options_parser.add_argument("--expiry-hint", type=str, help="Expiry hint (e.g., YYYYMMDD, YYYYMM, month name)")

    # Report command
    report_parser = subparsers.add_parser("report", help="Generate a trades report")
    report_parser.add_argument("--input", type=str, required=True, help="Path to trades CSV file")
    report_parser.add_argument("--output", type=str, default=f"trades_report_{get_timestamp()}.csv", help="Output file name")
    report_parser.add_argument("--format", type=str, default="csv", choices=["csv", "excel", "pdf"], help="Output format")

    # Orchestrate command
    orchestrate_parser = subparsers.add_parser("orchestrate", help="Run a sequence of commands")
    orchestrate_parser.add_argument("--format", type=str, default="csv", choices=["csv", "pdf"], help="Output format for the dataset")

    # Check if any command-line arguments were provided
    if len(sys.argv) > 1:
        args = parser.parse_args()
        if args.command == "pulse":
            cmd_pulse(args)
        elif args.command == "live":
            cmd_live(args)
        elif args.command == "options":
            cmd_options(args)
        elif args.command == "report":
            cmd_report(args)
        elif args.command == "orchestrate":
            cmd_orchestrate(args)
    else:
        # Interactive mode
        while True:
            print("\nSelect a command:")
            print("1. pulse (Daily pulse report)")
            print("2. live (Live quotes)")
            print("3. options (Option chains)")
            print("4. report (Trades report)")
            print("5. orchestrate (Dataset orchestration)")
            print("6. Exit")

            choice = input("Enter your choice (1-6): ")

            if choice == '1':
                tickers = input("Enter tickers (comma-separated, e.g., AAPL,MSFT; leave blank to fetch from IBKR): ")
                output = input(f"Enter output file name (default: pulse_{get_timestamp()}.csv): ") or f"pulse_{get_timestamp()}.csv"
                fmt = input("Enter output format (csv, excel, pdf; default: csv): ") or "csv"
                class Args:
                    pass
                args = Args()
                args.tickers = tickers
                args.output = output
                args.format = fmt
                cmd_pulse(args)
            elif choice == '2':
                tickers = input("Enter tickers (comma-separated, e.g., AAPL,MSFT): ")
                output = input(f"Enter output file name (default: live_quotes_{get_timestamp()}.csv): ") or f"live_quotes_{get_timestamp()}.csv"
                class Args:
                    pass
                args = Args()
                args.tickers = tickers
                args.output = output
                cmd_live(args)
            elif choice == '3':
                symbol = input("Enter stock symbol for option chain (e.g., SPY): ")
                expiry_hint = input("Enter expiry hint (optional, e.g., YYYYMMDD, YYYYMM, month name): ")
                class Args:
                    pass
                args = Args()
                args.symbol = symbol
                args.expiry_hint = expiry_hint if expiry_hint else None
                cmd_options(args)
            elif choice == '4':
                input_file = input("Enter path to trades CSV file: ")
                output = input(f"Enter output file name (default: trades_report_{get_timestamp()}.csv): ") or f"trades_report_{get_timestamp()}.csv"
                fmt = input("Enter output format (csv, excel, pdf; default: csv): ") or "csv"
                class Args:
                    pass
                args = Args()
                args.input = input_file
                args.output = output
                args.format = fmt
                cmd_report(args)
            elif choice == '5':
                fmt = input("Enter output format (csv, pdf; default: csv): ") or "csv"
                class Args:
                    pass
                args = Args()
                args.format = fmt
                cmd_orchestrate(args)
            elif choice == '6':
                print("Exiting.")
                break
            else:
                print("Invalid choice. Please try again.")


if __name__ == "__main__":
    main()
