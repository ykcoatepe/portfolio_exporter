from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import builtins
from rich.console import Console
from rich.table import Table

from portfolio_exporter.core import cli as core_cli
from portfolio_exporter.core import json as core_json
from portfolio_exporter.core import ui as core_ui

console = Console()


def input(prompt: str = "") -> str:
    # Use StatusBar-aware prompt so input is visible and persistent.
    try:
        return core_ui.prompt_input(prompt)
    except Exception:
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
    console.print("Hotkeys: s=Sync tickers, 0=Exit")
    console.print("Multi-select hint: e.g., 2,4")


def parse_args() -> argparse.Namespace:
    epilog = (
        "Examples:\n"
        "  python main.py --list-tasks\n"
        "  python main.py --dry-run --task snapshot-quotes\n"
        "  python main.py --workflow demo --dry-run\n"
    )
    parser = argparse.ArgumentParser(
        add_help=False, epilog=epilog, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="suppress banner & status output"
    )
    parser.add_argument(
        "--format",
        choices=["csv", "excel", "pdf"],
        default="csv",
        help="default output format",
    )
    parser.add_argument(
        "--json", action="store_true", help="emit JSON output for planning commands"
    )
    parser.add_argument(
        "--list-tasks", action="store_true", help="list available tasks and aliases"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="show execution plan without running tasks"
    )
    parser.add_argument("--workflow", help="expand a named workflow from memory")
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

def task_registry(fmt: str) -> dict[str, callable]:
    def snapshot_quotes() -> None:
        from portfolio_exporter.scripts import live_feed

        live_feed.run(fmt=fmt, include_indices=False)

    def portfolio_greeks() -> None:
        from portfolio_exporter.scripts import portfolio_greeks as _portfolio_greeks

        _portfolio_greeks.run(fmt=fmt)

    def option_chain_snapshot() -> None:
        from portfolio_exporter.scripts import option_chain_snapshot as _ocs

        _ocs.run(fmt=fmt)

    def trades_report() -> None:
        from portfolio_exporter.scripts import trades_report as _trades

        _trades.run(fmt=fmt)

    def daily_report() -> None:
        from portfolio_exporter.scripts import daily_report as _daily

        _daily.run(fmt=fmt)

    def netliq_export() -> None:
        from portfolio_exporter.scripts import net_liq_history_export as _netliq

        _netliq.run(fmt=fmt)

    return {
        "snapshot-quotes": snapshot_quotes,
        "quotes": snapshot_quotes,
        "snapshot": snapshot_quotes,
        "portfolio-greeks": portfolio_greeks,
        "greeks": portfolio_greeks,
        "option-chain-snapshot": option_chain_snapshot,
        "chain-snapshot": option_chain_snapshot,
        "trades-report": trades_report,
        "daily-report": daily_report,
        "netliq-export": netliq_export,
    }


def load_workflow_queue(name: str) -> list[str]:
    path = Path(".codex/memory.json")
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except Exception:
        return []
    submenu = data.get("workflows", {}).get("submenu_queue", {})
    return submenu.get(name, submenu.get("default", []))


def main() -> None:
    args = parse_args()
    quiet = args.quiet or os.getenv("PE_QUIET") not in (None, "", "0")
    status = None
    if not quiet:
        status = core_ui.StatusBar("Ready")
        status.update("Ready")
        console.rule("[bold cyan]AI-Managed Playbook")

    registry = task_registry(args.format)

    if args.list_tasks:
        names = sorted(registry.keys())
        if args.json:
            data = {
                "schema": {"id": "task_registry", "version": core_json.SCHEMA_VERSION},
                "tasks": names,
            }
            core_cli.print_json(data, quiet)
        else:
            txt = "\n".join(names)
            (print if quiet else console.print)(txt)
        return

    all_tasks: list[str] = []
    if getattr(args, "tasks", None):
        all_tasks.extend([t for t in args.tasks if t])
    if getattr(args, "tasks_csv", None):
        all_tasks.extend([t.strip() for t in str(args.tasks_csv).split(",") if t.strip()])
    if args.workflow:
        wf = load_workflow_queue(args.workflow)
        if wf:
            all_tasks.extend(wf)

    if args.dry_run:
        names = [t.strip().lower().replace(" ", "-") for t in all_tasks]
        if args.json:
            data = {
                "schema": {"id": "task_plan", "version": core_json.SCHEMA_VERSION},
                "plan": names,
            }
            core_cli.print_json(data, quiet)
        else:
            txt = "\n".join(names)
            (print if quiet else console.print)(txt)
        return

    if all_tasks:
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
