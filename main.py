from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.table import Table
from portfolio_exporter.menus.pre import _input as menu_input
import builtins

from portfolio_exporter.core.ui import StatusBar

console = Console()
input = builtins.input


def build_menu() -> None:
    table = Table(title="AI-Managed Playbook – Main Menu")
    table.add_column("#")
    table.add_column("Function")
    table.add_row("1", "Pre-Market")
    table.add_row("2", "Live-Market")
    table.add_row("3", "Trades & Reports")
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


def main() -> None:
    args = parse_args()
    status = None
    if not args.quiet:
        status = StatusBar("Ready")
        status.update("Ready")
        console.rule("[bold cyan]AI-Managed Playbook")

    while True:
        build_menu()
        raw = menu_input("Select › ")
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
            console.print("[red]Invalid choice")

    if status:
        status.stop()


if __name__ == "__main__":
    main()
