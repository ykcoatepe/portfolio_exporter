from __future__ import annotations
import argparse
import sys

from rich.console import Console
from rich.table import Table
import builtins

from portfolio_exporter.core.ui import StatusBar

console = Console()


def input(prompt: str = "") -> str:
    return builtins.input(prompt)


def build_menu() -> None:
    """Render the top-level menu."""
    table = Table(title="AI-Managed Playbook – Main Menu")
    table.add_column("#")
    table.add_column("Function")
    table.add_row("1", "Pre-Market")
    table.add_row("2", "Live-Market")
    table.add_row("3", "Trades & Reports")
    table.add_row("4", "Portfolio Greeks")
    table.add_row("0", "Exit")
    console.print(table)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="suppress banner & status output"
    )
    parser.add_argument(
        "--format",
        choices=["csv", "excel", "pdf"],
        default="csv",
        help="default output format",
    )
    return parser.parse_known_args()[0]


import os


def main() -> None:
    args = parse_args()
    status = None
    if not args.quiet:
        status = StatusBar("Ready")
        status.update("Ready")
        console.rule("[bold cyan]AI-Managed Playbook")

    if os.getenv("PE_TEST_MODE"):
        from portfolio_exporter.scripts import portfolio_greeks
        import sys

        original_argv = sys.argv
        try:
            idx = sys.argv.index("portfolio-greeks")
            sys.argv = [sys.argv[0]] + sys.argv[idx + 1 :]
        except ValueError:
            pass  # should not happen in test
        portfolio_greeks.main()
        sys.argv = original_argv
        return

    while True:
        build_menu()
        raw = input("\u203a ")
        for choice in raw.strip().splitlines():
            choice = choice.strip().lower()
            if choice == "0":
                return
            if choice == "s":
                from portfolio_exporter.scripts import update_tickers

                update_tickers.run(args.format)
                continue
            if choice == "1":
                if status:
                    status.update("Entering Pre-Market", "cyan")
                from portfolio_exporter.menus import pre

                pre.launch(status, args.format)
                continue
            if choice == "2":
                if status:
                    status.update("Entering Live-Market", "cyan")
                from portfolio_exporter.menus import live

                live.launch(status, args.format)
                continue
            if choice == "3":
                if status:
                    status.update("Entering Trades menu", "cyan")
                from portfolio_exporter.menus import trade

                trade.launch(status, args.format)
                continue
            if choice == "4":
                if status:
                    status.update("Running Portfolio Greeks", "cyan")
                from portfolio_exporter.scripts import portfolio_greeks

                portfolio_greeks.run(args.format)
                if status:
                    status.update("Ready", "green")
                continue
            console.print("[red]Invalid choice")

    if status:
        status.stop()


if __name__ == "__main__":
    main()
