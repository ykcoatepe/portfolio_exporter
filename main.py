from __future__ import annotations
import argparse
import re
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
    # Queue support: allow multiple --task flags or a single comma-separated --tasks
    parser.add_argument(
        "--task",
        action="append",
        dest="tasks",
        help=(
            "Task to run (repeatable). Known: snapshot-quotes, portfolio-greeks, "
            "option-chain-snapshot, trades-report, daily-report, netliq-export"
        ),
    )
    parser.add_argument(
        "--tasks",
        dest="tasks_csv",
        help="Comma-separated tasks (alternative to repeatable --task)",
    )
    parser.add_argument(
        "--stop-on-fail",
        action="store_true",
        help="Stop the queued run at first failure",
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

    # If tasks provided, run in non-interactive queued mode
    all_tasks: list[str] = []
    if getattr(args, "tasks", None):
        all_tasks.extend([t for t in args.tasks if t])
    if getattr(args, "tasks_csv", None):
        all_tasks.extend([t.strip() for t in str(args.tasks_csv).split(",") if t.strip()])

    if all_tasks:
        # Map user-friendly names to script callables
        from portfolio_exporter.scripts import (
            live_feed,
            portfolio_greeks as _portfolio_greeks,
            option_chain_snapshot as _ocs,
            trades_report as _trades,
            daily_report as _daily,
            net_liq_history_export as _netliq,
        )

        registry: dict[str, callable] = {
            # aliases for quotes snapshot
            "snapshot-quotes": lambda: live_feed.run(fmt=args.format, include_indices=False),
            "quotes": lambda: live_feed.run(fmt=args.format, include_indices=False),
            "snapshot": lambda: live_feed.run(fmt=args.format, include_indices=False),
            # portfolio greeks
            "portfolio-greeks": lambda: _portfolio_greeks.run(fmt=args.format),
            "greeks": lambda: _portfolio_greeks.run(fmt=args.format),
            # option chain snapshot (full chain export)
            "option-chain-snapshot": lambda: _ocs.run(fmt=args.format),
            "chain-snapshot": lambda: _ocs.run(fmt=args.format),
            # reports
            "trades-report": lambda: _trades.run(fmt=args.format),
            "daily-report": lambda: _daily.run(fmt=args.format),
            "netliq-export": lambda: _netliq.run(fmt=args.format),
        }

        failures: list[str] = []
        for name in all_tasks:
            key = name.strip().lower().replace(" ", "-")
            fn = registry.get(key)
            if not fn:
                console.print(f"[red]Unknown task:[/] {name}")
                failures.append(name)
                if args.stop_on_fail:
                    break
                continue
            if status:
                status.update(f"Running {key}", "cyan")
            try:
                fn()
            except Exception as exc:
                console.print(f"[red]Task failed:[/] {key} → {exc}")
                failures.append(key)
                if args.stop_on_fail:
                    break
            finally:
                if status:
                    status.update("Ready", "green")

        # Summary and exit queued mode
        if failures:
            console.print(f"[yellow]Completed with {len(failures)} failure(s): {failures}")
        return

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
        # Accept multiple numeric choices separated by spaces or commas (e.g., "2,4")
        tokens = [t for t in re.split(r"[\s,]+", raw.strip()) if t]
        for choice in tokens:
            if choice == "0":
                return
            if choice == "s":
                from portfolio_exporter.scripts import update_tickers

                update_tickers.run(args.format)
                continue
            # Only numeric choices are supported for queued input
            if choice not in {"1", "2", "3", "4"}:
                console.print("[red]Invalid choice")
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
