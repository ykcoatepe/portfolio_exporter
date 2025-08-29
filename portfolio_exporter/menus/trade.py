from __future__ import annotations

import builtins as _builtins
import os
from contextlib import contextmanager

from rich.console import Console
from rich.table import Table

from portfolio_exporter.core.ui import prompt_input


@contextmanager
def _temp_attr(obj, name: str, value):
    """Temporarily set ``obj.name`` to ``value``."""

    orig = getattr(obj, name, None)
    setattr(obj, name, value)
    try:
        yield
    finally:
        if orig is None:
            delattr(obj, name)
        else:
            setattr(obj, name, orig)


def _build_synth_chain():
    """Return a minimal chain DataFrame based on latest positions CSV."""

    import pandas as pd
    from portfolio_exporter.core.io import latest_file

    path = latest_file("portfolio_greeks_positions")
    if not path:
        return pd.DataFrame(columns=["symbol", "strike", "right", "mid", "delta", "gamma", "theta", "vega"])
    try:
        df = pd.read_csv(path)
    except Exception:
        return pd.DataFrame(columns=["symbol", "strike", "right", "mid", "delta", "gamma", "theta", "vega"])
    rows = []
    for _, row in df.drop_duplicates(["underlying", "right", "strike"]).iterrows():
        rows.append(
            {
                "symbol": row.get("underlying"),
                "strike": row.get("strike"),
                "right": row.get("right"),
                "mid": row.get("mid", 0),
                "delta": row.get("delta", 0),
                "gamma": row.get("gamma", 0),
                "theta": row.get("theta", 0),
                "vega": row.get("vega", 0),
            }
        )
    return pd.DataFrame(rows)

# Menu for trade-related utilities


def launch(status, default_fmt):
    console = status.console if status else Console()

    def _preview_daily_report() -> None:
        orig_quiet = os.getenv("PE_QUIET")
        os.environ["PE_QUIET"] = "1"
        try:
            from portfolio_exporter.scripts import daily_report as _daily

            summary = _daily.main(["--json", "--no-files"])
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

    def _preflight_daily_report() -> None:
        orig_quiet = os.getenv("PE_QUIET")
        os.environ["PE_QUIET"] = "1"
        try:
            from portfolio_exporter.scripts import daily_report as _daily

            summary = _daily.main(["--preflight", "--json", "--no-files"])
        except Exception as exc:  # pragma: no cover - defensive
            console.print(f"[red]Preflight failed:[/] {exc}")
        else:
            for w in summary.get("warnings", []):
                console.print(f"[yellow]{w}")
        finally:
            if orig_quiet is None:
                os.environ.pop("PE_QUIET", None)
            else:
                os.environ["PE_QUIET"] = orig_quiet

    def _preview_trades_clusters() -> None:
        orig_quiet = os.getenv("PE_QUIET")
        os.environ["PE_QUIET"] = "1"
        try:
            from portfolio_exporter.scripts import trades_report as _trades

            summary = _trades.main(["--summary-only", "--json", "--no-files"])
        except Exception as exc:  # pragma: no cover - defensive
            console.print(f"[red]Preview failed:[/] {exc}")
        else:
            sections = summary.get("sections", {})
            console.print(f"Executions: {sections.get('executions', 0)}")
            console.print(f"Clusters: {sections.get('clusters', 0)}")
            console.print(f"Combos: {sections.get('combos', 0)}")
            for w in summary.get("warnings", []):
                console.print(f"[yellow]{w}")
        finally:
            if orig_quiet is None:
                os.environ.pop("PE_QUIET", None)
            else:
                os.environ["PE_QUIET"] = orig_quiet

    def _run_roll_manager(args: list[str]) -> dict | None:
        from portfolio_exporter.scripts import roll_manager as _rm

        rm_main = getattr(_rm, "main", _rm.cli)
        try:
            return rm_main(args)
        except Exception:
            chain_df = _build_synth_chain()
            if chain_df.empty:
                console.print("[yellow]Missing positions; run: portfolio-greeks")
                return None
            with _temp_attr(_rm, "fetch_chain", lambda *a, **k: chain_df):
                return rm_main(args)

    def _preview_roll_manager() -> None:
        orig_quiet = os.getenv("PE_QUIET")
        os.environ["PE_QUIET"] = "1"
        try:
            summary = _run_roll_manager(["--dry-run", "--json", "--no-files"])
            if summary is None:
                return
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

    def _preflight_roll_manager() -> None:
        orig_quiet = os.getenv("PE_QUIET")
        os.environ["PE_QUIET"] = "1"
        from portfolio_exporter.core.io import latest_file

        if not latest_file("portfolio_greeks_positions"):
            console.print("[yellow]Missing positions; run: portfolio-greeks")
            if orig_quiet is None:
                os.environ.pop("PE_QUIET", None)
            else:
                os.environ["PE_QUIET"] = orig_quiet
            return
        try:
            summary = _run_roll_manager(["--dry-run", "--json", "--no-files"])
            if summary is None:
                return
            for w in summary.get("warnings", []):
                console.print(f"[yellow]{w}")
            if not summary.get("warnings"):
                console.print(f"Candidates: {len(summary.get('candidates', []))}")
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
            ("c", "Preview Trades Clusters (JSON-only)"),
            ("q", "Quick option chain"),
            ("n", "Net-Liq (CLI)"),
            ("d", "Generate Daily Report"),
            ("p", "Preview Daily Report (JSON-only)"),
            ("f", "Preflight Daily Report"),
            ("x", "Preflight Roll Manager"),
            ("r", "Return"),
        ]
        tbl = Table(title="Trades & Reports")
        for k, lbl in entries:
            tbl.add_row(k, lbl)
        console.print(tbl)
        console.print("Multi-select hint: e.g., v p")
        try:
            raw = prompt_input("› ")
        except Exception:
            raw = _builtins.input("› ")
        raw = raw.strip().lower()
        import re as _re

        tokens = [t for t in _re.split(r"[\s,]+", raw) if t]
        for ch in tokens:
            if ch == "r":
                return
            label_map = dict(entries)

            def _trades_report() -> None:
                from portfolio_exporter.scripts import trades_report as _tr

                _tr.run(fmt=default_fmt, show_actions=True)

            def _order_builder() -> None:
                from portfolio_exporter.scripts import order_builder as _ob

                _ob.run()

            def _roll_positions() -> None:
                from portfolio_exporter.scripts import roll_manager as _rm

                _rm.run()

            def _quick_chain() -> None:
                from portfolio_exporter.scripts import option_chain_snapshot as _ocs

                _ocs.run(fmt=default_fmt)

            def _net_liq() -> None:
                from portfolio_exporter.scripts import net_liq_history_export as _netliq

                _netliq.main(["--quiet", "--no-pretty"] if os.getenv("PE_QUIET") else [])

            def _generate_daily_report() -> None:
                from portfolio_exporter.scripts import daily_report as _daily

                fmt_flag = {"pdf": "--pdf", "excel": "--excel"}.get(default_fmt, "--html")
                args = [fmt_flag]
                if os.getenv("PE_QUIET"):
                    args.append("--no-pretty")
                _daily.main(args)

            dispatch = {
                "e": _trades_report,
                "b": _order_builder,
                "l": _roll_positions,
                "v": _preview_roll_manager,
                "c": _preview_trades_clusters,
                "q": _quick_chain,
                "n": _net_liq,
                "d": _generate_daily_report,
                "p": _preview_daily_report,
                "f": _preflight_daily_report,
                "x": _preflight_roll_manager,
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
