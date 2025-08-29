from rich.console import Console
import builtins as _builtins
from rich.table import Table
from portfolio_exporter.scripts import (
    trades_report,
    order_builder,
    roll_manager,
    option_chain_snapshot,
    net_liq_history_export,
    daily_report,
)
import os

# Menu for trade-related utilities


def launch(status, default_fmt):
    console = status.console if status else Console()

    def _preview_daily_report() -> None:
        orig_quiet = os.getenv("PE_QUIET")
        os.environ["PE_QUIET"] = "1"
        try:
            summary = daily_report.main(["--json", "--no-files"])
        except Exception as exc:  # pragma: no cover - defensive
            console.print(f"[red]Preview failed:[/] {exc}")
        else:
            sections = summary.get("sections", {})
            console.print(f"Positions: {sections.get('positions', 0)}")
            console.print(f"Combos: {sections.get('combos', 0)}")
            console.print(f"Totals: {sections.get('totals', 0)}")
            radar = summary.get("expiry_radar")
            if radar:
                console.print(f"Expiry radar: {radar}")
            for w in summary.get("warnings", []):
                console.print(f"[yellow]{w}")
        finally:
            if orig_quiet is None:
                os.environ.pop("PE_QUIET", None)
            else:
                os.environ["PE_QUIET"] = orig_quiet

    def _preview_roll_manager() -> None:
        orig_quiet = os.getenv("PE_QUIET")
        os.environ["PE_QUIET"] = "1"
        try:
            summary = roll_manager.cli(["--dry-run", "--json", "--no-files"])
        except Exception as exc:  # pragma: no cover - defensive
            console.print(f"[red]Preview failed:[/] {exc}")
        else:
            candidates = summary.get("candidates", [])
            console.print(f"Candidates: {len(candidates)}")
            top = sorted(candidates, key=lambda c: abs(c.get("delta", 0)), reverse=True)[:3]
            for c in top:
                console.print(
                    f"{c.get('underlying')} Δ{c.get('delta', 0):+0.2f} {c.get('debit_credit', 0):+0.2f}"
                )
            for w in summary.get("warnings", []):
                console.print(f"[yellow]{w}")
        finally:
            if orig_quiet is None:
                os.environ.pop("PE_QUIET", None)
            else:
                os.environ["PE_QUIET"] = orig_quiet

    while True:
        entries = [
            ("e", "Executions / open orders"),
            ("b", "Build order"),
            ("l", "Roll positions"),
            ("v", "Preview Roll Manager (dry-run)"),
            ("q", "Quick option chain"),
            ("n", "Net-Liq (CLI)"),
            ("d", "Daily report (HTML/PDF)"),
            ("p", "Preview Daily Report (JSON-only)"),
            ("r", "Return"),
        ]
        tbl = Table(title="Trades & Reports")
        for k, lbl in entries:
            tbl.add_row(k, lbl)
        console.print(tbl)
        try:
            raw = __import__("main").input("› ")
        except Exception:
            raw = _builtins.input("› ")
        raw = raw.strip().lower()
        # Allow multiple entries separated by spaces or commas
        import re as _re
        tokens = [t for t in _re.split(r"[\s,]+", raw) if t]
        for ch in tokens:
            if ch == "r":
                return
            label_map = dict(entries)
            dispatch = {
                "e": lambda: trades_report.run(fmt=default_fmt, show_actions=True),
                "b": order_builder.run,
                "l": lambda: roll_manager.run(),
                "v": _preview_roll_manager,
                "q": lambda: option_chain_snapshot.run(fmt=default_fmt),
                "n": lambda: net_liq_history_export.main(
                    ["--quiet", "--no-pretty"] if os.getenv("PE_QUIET") else []
                ),
                "d": lambda: daily_report.main(
                    ["--no-pretty"] if os.getenv("PE_QUIET") else []
                ),
                "p": _preview_daily_report,
            }.get(ch)
            if dispatch:
                label = label_map.get(ch, ch)
                if status:
                    status.update(f"Running {label} …", "cyan")
                try:
                    dispatch()
                except Exception as exc:
                    console.print(f"[red]Error running {label}:[/] {exc}")
                finally:
                    if status:
                        status.update("Ready", "green")
