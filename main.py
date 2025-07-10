from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.table import Table
from builtins import input as builtin_input

input = builtin_input

from portfolio_exporter.core.ui import StatusBar

console = Console()


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
        choice = input("Select › ").strip()
        if choice == "0":
            break
        elif choice not in {"1", "2", "3"}:
            console.print("[red]Invalid choice")
        else:
            if choice == "1":
                if status:
                    status.update("Entering Pre-Market", "cyan")
                from portfolio_exporter.menus import pre
                pre.launch(status, args.format)
            else:
                console.print(f"(stub) You chose {choice}")

    if status:
        status.stop()


if __name__ == "__main__":
    main()
