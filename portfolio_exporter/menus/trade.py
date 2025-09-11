from __future__ import annotations

from __future__ import annotations

import builtins as _builtins
import os
from contextlib import contextmanager
from pathlib import Path

import json

try:
    from rich.console import Console
    from rich.table import Table
except Exception:  # pragma: no cover - fallback for constrained test envs
    class Console:  # type: ignore
        def print(self, *a, **_k):
            try:
                print(*a)
            except Exception:
                pass
    class Table:  # type: ignore
        def __init__(self, *a, **k):
            pass
        def add_column(self, *a, **k):
            pass
        def add_row(self, *a, **k):
            pass

from portfolio_exporter.core import ui as core_ui
# Back-compat: allow tests to monkeypatch prompt_input on this module
prompt_input = core_ui.prompt_input
import datetime as _dt

# Speed up previews in CI/test mode
import os as _os
TEST_MODE = bool(_os.getenv("PE_TEST_MODE"))


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


def _resolve_last_report(prefer: str | None = "daily") -> Path | None:
    """Return most recent report Path based on preference."""

    from portfolio_exporter.core.io import latest_file

    order = ["daily", "dashboard"]
    if prefer in order:
        order.remove(prefer)
        order.insert(0, prefer)
    mapping = {"daily": "daily_report", "dashboard": "trades_dashboard"}
    for kind in order:
        base = mapping[kind]
        for fmt in ("html", "pdf"):
            path = latest_file(base, fmt)
            if path:
                return path
    return None


def open_last_report(prefer: str | None = None, quiet: bool = False) -> str:
    """Print and optionally open the most recent report."""

    path = _resolve_last_report(prefer)
    if not path:
        return "No report found"
    print(path)
    if not quiet and os.getenv("PE_QUIET") in (None, "", "0"):
        try:  # pragma: no cover - best effort
            import webbrowser

            webbrowser.open(str(path))
        except Exception:
            pass
    return f"Opened {path.name}"


def _tr_parser_supports(name: str) -> bool:
    """Return True if trades_report parser has an option with this name.

    Defensive: any import or attribute error returns False.
    """
    try:  # pragma: no cover - light guard
        from portfolio_exporter.scripts import trades_report as TR

        p = TR.get_arg_parser()
        return any(name in a.option_strings for a in getattr(p, "_actions", []))
    except Exception:
        return False


def _quick_save_filtered(
    *,
    output_dir: str,
    symbols: str | None = None,
    effect_in: str | None = None,
    structure_in: str | None = None,
    top_n: int | None = None,
    quiet: bool = False,
) -> dict:
    """Run trades_report with filters and return JSON summary."""

    from portfolio_exporter.scripts import trades_report as _tr

    argv = ["--json", "--output-dir", output_dir]
    if symbols and _tr_parser_supports("--symbol"):
        argv.extend(["--symbol", symbols])
    if effect_in and _tr_parser_supports("--effect-in"):
        argv.extend(["--effect-in", effect_in])
    if structure_in and _tr_parser_supports("--structure-in"):
        argv.extend(["--structure-in", structure_in])
    if top_n is not None and _tr_parser_supports("--top-n"):
        argv.extend(["--top-n", str(top_n)])
    summary = _tr.main(argv)
    if not quiet:
        for p in summary.get("outputs", []):
            if p:
                print(p)
    return summary


def _preview_trades_json(
    *,
    symbols: str | None = None,
    effect_in: str | None = None,
    structure_in: str | None = None,
    top_n: int | None = None,
) -> str:
    """Return prettified JSON summary from trades_report."""

    from portfolio_exporter.scripts import trades_report as _tr

    argv = ["--json", "--no-files"]
    if symbols and _tr_parser_supports("--symbol"):
        argv.extend(["--symbol", symbols])
    if effect_in and _tr_parser_supports("--effect-in"):
        argv.extend(["--effect-in", effect_in])
    if structure_in and _tr_parser_supports("--structure-in"):
        argv.extend(["--structure-in", structure_in])
    if top_n is not None and _tr_parser_supports("--top-n"):
        argv.extend(["--top-n", str(top_n)])
    data = _tr.main(argv)
    return json.dumps(data, indent=2, sort_keys=True)


def _copy_to_clipboard(text: str) -> bool:
    """Copy *text* to system clipboard if pyperclip is available."""

    try:
        import pyperclip  # type: ignore
    except Exception:  # pragma: no cover - optional dependency
        return False
    try:
        pyperclip.copy(text)
    except Exception:  # pragma: no cover - best effort
        return False
    return True

# Menu for trade-related utilities


def launch(status, default_fmt):
    console = status.console if status else Console()
    # Simple per-session cache for heavy data
    session: dict = {}
    current_fmt = default_fmt

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
        # Silence pandera import deprecation noise during preflight
        orig_pandera = os.getenv("DISABLE_PANDERA_IMPORT_WARNING")
        os.environ["DISABLE_PANDERA_IMPORT_WARNING"] = "TRUE"
        try:
            from portfolio_exporter.scripts import daily_report as _daily
            from portfolio_exporter.core.config import settings as _settings

            summary = _daily.main(["--preflight", "--json", "--no-files"])
            # If inputs are missing, auto-run Portfolio Greeks then re-run preflight
            warns = [str(w).lower() for w in summary.get("warnings", [])]
            needs_refresh = any(
                ("missing positions" in w) or ("missing totals" in w) or ("missing combos" in w)
                for w in warns
            )
            if needs_refresh:
                console.print("[yellow]Inputs missing; auto-generating Portfolio Greeks …")
                try:
                    from portfolio_exporter.scripts import portfolio_greeks as _pg
                    # Write fresh CSVs to configured OUTPUT_DIR
                    _pg.main(["--output-dir", str(_settings.output_dir), "--json"])  # quiet via PE_QUIET
                except Exception as exc:
                    console.print(f"[red]Auto-generation failed:[/] {exc}")
                else:
                    # Re-run preflight
                    summary = _daily.main(["--preflight", "--json", "--no-files"]) 
        except Exception as exc:  # pragma: no cover - defensive
            console.print(f"[red]Preflight failed:[/] {exc}")
        else:
            for w in summary.get("warnings", []):
                console.print(f"[yellow]{w}")
            if not summary.get("warnings"):
                console.print("Preflight OK: files can be generated.")
        finally:
            if orig_quiet is None:
                os.environ.pop("PE_QUIET", None)
            else:
                os.environ["PE_QUIET"] = orig_quiet
            if orig_pandera is None:
                os.environ.pop("DISABLE_PANDERA_IMPORT_WARNING", None)
            else:
                os.environ["DISABLE_PANDERA_IMPORT_WARNING"] = orig_pandera

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
                exp = c.get("expiry") or c.get("exp")
                dte_txt = ""
                try:
                    if exp:
                        dte = ( _dt.date.fromisoformat(str(exp)) - _dt.date.today() ).days
                        dte_txt = f" {exp} ({dte}D)"
                except Exception:
                    dte_txt = ""
                console.print(f"{c.get('underlying')} Δ{c.get('delta', 0):+0.2f} {c.get('debit_credit', 0):+0.2f}{dte_txt}")
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
            console.print("[yellow]Missing positions; run: portfolio-greeks (hint: PE_POSITIONS_MAX_AGE_SEC controls freshness)")
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
            ("o", "Open last report (HTML/PDF)"),
            ("k", "Open last order ticket (JSON)"),
            ("s", "Save filtered trades CSV… (choose filters)"),
            ("j", "Copy trades JSON summary (filtered)"),
            ("m", "Preview Combos MTM P&L (JSON-only)"),
            ("t", f"Toggle output format (current: {current_fmt})"),
            ("r", "Return"),
        ]
        tbl = Table(title="Trades & Reports")
        for k, lbl in entries:
            tbl.add_row(k, lbl)
        console.print(tbl)
        console.print("Multi-select hint: e.g., v p")
        try:
            raw = core_ui.prompt_input("› ")
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
                # Generate report in selected format
                df = _tr.run(fmt=current_fmt, show_actions=True, return_df=True)
                try:
                    session["execs_df"] = df
                except Exception:
                    pass
                # Quick intent summary (Open/Close/Roll/Mixed) using JSON-only pass
                try:
                    buf = io.StringIO()
                    import contextlib as _ctx
                    # Use default prior positions from memory if present
                    args = ["--summary-only", "--json", "--no-files"]
                    if not TEST_MODE:
                        try:
                            from pathlib import Path as _Path
                            _pf = _Path(".codex/memory.json")
                            if _pf.exists():
                                _data = json.loads(_pf.read_text())
                                prior = (_data.get("preferences", {}) or {}).get("trades_prior_positions", "")
                                if prior and _Path(prior).expanduser().exists():
                                    args.extend(["--prior-positions-csv", str(_Path(prior).expanduser())])
                        except Exception:
                            pass
                    with _ctx.redirect_stdout(buf):
                        _tr.main(args)
                    summary = json.loads(buf.getvalue().strip() or "{}")
                    intent = (summary.get("meta", {}) or {}).get("intent", {})
                    rows = intent.get("rows", {}) or {}
                    by_und = intent.get("by_underlying", []) or []
                    # Print high-level counts
                    if rows:
                        console.print(
                            f"Intent: Open={rows.get('Open',0)} Close={rows.get('Close',0)} Roll={rows.get('Roll',0)} Mixed={rows.get('Mixed',0)} Unknown={rows.get('Unknown',0)}"
                        )
                    # Print top few underlyings by activity with their dominant effect
                    if by_und:
                        try:
                            top = by_und[:5]
                            txt = ", ".join(f"{r.get('underlying')}: {r.get('position_effect')}" for r in top if r.get('underlying'))
                            if txt:
                                console.print(f"By underlying: {txt}")
                        except Exception:
                            pass
                    # If Unknown ratio is high or prior snapshot warning present, offer override
                    try:
                        unk = int(rows.get('Unknown', 0))
                        total = sum(int(rows.get(k, 0)) for k in ['Open','Close','Roll','Mixed','Unknown']) or 1
                        warnings = summary.get('warnings', []) or []
                        need_prior = (unk / total) > 0.3 or any('prior positions snapshot' in str(w).lower() for w in warnings)
                    except Exception:
                        need_prior = False
                    if need_prior:
                        path = core_ui.prompt_input("Prior positions CSV path to improve intent (Enter to skip): ").strip()
                        if path:
                            buf2 = io.StringIO()
                            with _ctx.redirect_stdout(buf2):
                                _tr.main(["--summary-only", "--json", "--no-files", "--prior-positions-csv", path])
                            s2 = json.loads(buf2.getvalue().strip() or "{}")
                            rows2 = ((s2.get("meta", {}) or {}).get("intent", {}) or {}).get("rows", {}) or {}
                            if rows2:
                                console.print(
                                    f"Updated intent with prior: Open={rows2.get('Open',0)} Close={rows2.get('Close',0)} Roll={rows2.get('Roll',0)} Mixed={rows2.get('Mixed',0)} Unknown={rows2.get('Unknown',0)}"
                                )
                            # Persist for future runs
                            try:
                                from pathlib import Path as _Path
                                _pf = _Path(".codex/memory.json")
                                data = {}
                                if _pf.exists():
                                    data = json.loads(_pf.read_text())
                                prefs = data.setdefault("preferences", {})
                                prefs["trades_prior_positions"] = str(_Path(path).expanduser())
                                tmp = _pf.with_suffix(".json.tmp")
                                tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
                                os.replace(tmp, _pf)
                            except Exception:
                                pass
                except Exception:
                    pass
                # Top combos by realized P&L (from clustered executions)
                try:
                    import pandas as _pd  # local import to avoid heavy deps at import time
                    if isinstance(df, _pd.DataFrame) and not df.empty:
                        execs = df[df.get("exec_id").notna()] if "exec_id" in df.columns else df
                        clusters, _dbg = _tr._cluster_executions(execs)
                        # Build mapping: combo perm_ids → position_effect
                        effect_map: list[tuple[set[int], str]] = []
                        try:
                            # Resolve a strictly prior positions snapshot to improve intent
                            earliest = None
                            try:
                                earliest = _tr._get_earliest_exec_ts(execs)
                            except Exception:
                                earliest = None
                            prior_override = None
                            try:
                                from pathlib import Path as _Path
                                _pf = _Path(".codex/memory.json")
                                if _pf.exists():
                                    _data = json.loads(_pf.read_text())
                                    prior_override = (_data.get("preferences", {}) or {}).get("trades_prior_positions", "") or None
                            except Exception:
                                prior_override = None
                            prior_df = None
                            try:
                                from portfolio_exporter.core.config import settings as _settings
                                search_dirs = []
                                try:
                                    from pathlib import Path as _P
                                    search_dirs = [_P(str(_settings.output_dir))]
                                    td = _P("tests/data")
                                    if td.exists():
                                        search_dirs.append(td)
                                except Exception:
                                    search_dirs = []
                                prior_df, _prior_path = _tr._ensure_prev_positions_quiet(earliest, _settings.output_dir, prior_override, search_dirs)
                            except Exception:
                                prior_df = None
                            combos_df = _tr._detect_and_enrich_trades_combos(execs, None, prev_positions_df=prior_df)
                            try:
                                session["combos_df"] = combos_df
                                session["prior_df"] = prior_df
                            except Exception:
                                pass
                            if isinstance(combos_df, _pd.DataFrame) and not combos_df.empty:
                                def _to_set(s: object) -> set[int]:
                                    vals = set()
                                    for tok in str(s or "").replace("/", ",").split(","):
                                        tok = tok.strip()
                                        if not tok:
                                            continue
                                        try:
                                            vals.add(int(tok))
                                        except Exception:
                                            pass
                                    return vals
                                for _, r in combos_df.iterrows():
                                    ids = _to_set(r.get("order_ids", ""))
                                    eff = str(r.get("position_effect", "Unknown"))
                                    if ids:
                                        effect_map.append((ids, eff))
                        except Exception:
                            effect_map = []
                        if isinstance(clusters, _pd.DataFrame) and not clusters.empty and "pnl" in clusters.columns:
                            try:
                                session["clusters_df"] = clusters
                            except Exception:
                                pass
                            top = clusters.copy()
                            # Sort by absolute P&L
                            try:
                                top = top.reindex(top["pnl"].abs().sort_values(ascending=False).index)
                            except Exception:
                                top = top.sort_values("pnl", ascending=False)
                            top = top.head(5)
                            tbl = Table(title="Top Combos by Realized P&L")
                            tbl.add_column("Underlying")
                            tbl.add_column("Structure")
                            tbl.add_column("Legs", justify="right")
                            tbl.add_column("Effect")
                            tbl.add_column("P&L", justify="right")
                            tbl.add_column("Start")
                            tbl.add_column("End")
                            for _, r in top.iterrows():
                                und = str(r.get("underlying", ""))
                                struct = str(r.get("structure", ""))
                                legs_n = str(int(r.get("legs_n", 0))) if _pd.notna(r.get("legs_n")) else ""
                                pnl = float(r.get("pnl", 0.0)) if _pd.notna(r.get("pnl")) else 0.0
                                start = str(r.get("start", ""))
                                end = str(r.get("end", ""))
                                # Derive effect by intersecting cluster perm_ids with combo order_ids
                                effect = ""
                                try:
                                    perm_set = set()
                                    for tok in str(r.get("perm_ids", "")).replace("/", ",").split(","):
                                        tok = tok.strip()
                                        if tok:
                                            perm_set.add(int(tok))
                                    # Priority: Roll > Close > Open > Mixed > Unknown
                                    priority = {"Roll": 4, "Close": 3, "Open": 2, "Mixed": 1, "Unknown": 0}
                                    best = ("", -1)
                                    for ids, eff in effect_map:
                                        if ids and perm_set.intersection(ids):
                                            pr = priority.get(eff, 0)
                                            if pr > best[1]:
                                                best = (eff, pr)
                                    effect = best[0] or ""
                                except Exception:
                                    effect = ""
                                tbl.add_row(und, struct, legs_n, effect, f"{pnl:+.2f}", start, end)
                            console.print(tbl)
                except Exception:
                    pass

            def _order_builder() -> None:
                from portfolio_exporter.scripts import order_builder as _ob
                from portfolio_exporter.core.io import save as io_save
                import json, io, contextlib

                while True:
                    tbl = Table(title="Stage Order")
                    opts = [("p", "Preset"), ("w", "Wizard"), ("r", "Return")]
                    for k, lbl in opts:
                        tbl.add_row(k, lbl)
                    console.print(tbl)
                    ch = core_ui.prompt_input("› ").strip().lower()
                    if ch == "r":
                        return
                    if ch == "w":
                        _ob.run()
                        continue
                    if ch != "p":
                        continue
                    presets = [
                        "bull_put",
                        "bear_call",
                        "bull_call",
                        "bear_put",
                        "iron_condor",
                        "iron_fly",
                        "butterfly",
                        "calendar",
                    ]
                    tbl = Table(title="Preset")
                    for i, p in enumerate(presets, 1):
                        tbl.add_row(str(i), p)
                    console.print(tbl)
                    sel = core_ui.prompt_input("Preset #: ").strip()
                    try:
                        preset = presets[int(sel) - 1]
                    except Exception:
                        console.print("[red]Invalid preset[/red]")
                        continue
                    # Prefill symbol/expiry defaults from Pre-Market menu cache
                    try:
                        from portfolio_exporter.menus import pre as _pre_menu
                        _last_sym = _pre_menu.last_symbol.get()
                        _last_exp = _pre_menu.last_expiry.get()
                    except Exception:
                        _last_sym, _last_exp = "", ""
                    sym_prompt = f"Symbol [{_last_sym}]: " if _last_sym else "Symbol: "
                    exp_prompt = (
                        f"Expiry (YYYY-MM-DD or month like 'nov') [{_last_exp}]: "
                        if _last_exp
                        else "Expiry (YYYY-MM-DD or month like 'nov'): "
                    )
                    symbol = (core_ui.prompt_input(sym_prompt).strip().upper() or _last_sym).upper()
                    expiry = core_ui.prompt_input(exp_prompt).strip() or _last_exp
                    # Update last symbol/expiry cache
                    try:
                        if symbol:
                            _pre_menu.last_symbol.value = symbol
                        if expiry:
                            _pre_menu.last_expiry.value = expiry
                    except Exception:
                        pass
                    qty = core_ui.prompt_input("Qty [1]: ").strip() or "1"

                    # Optional: auto-select strikes for supported presets using live data
                    if preset in {"bull_put", "bear_call", "bull_call", "bear_put", "iron_condor", "butterfly", "calendar"}:
                        auto = core_ui.prompt_input("Auto-select strikes from live data? (Y/n) [Y]: ").strip().lower()
                        if auto in {"", "y"}:
                            from portfolio_exporter.core.preset_engine import (
                                suggest_credit_vertical,
                                suggest_debit_vertical,
                                suggest_iron_condor,
                                suggest_butterfly,
                                suggest_calendar,
                                LiquidityRules,
                            )
                            from portfolio_exporter.scripts.order_builder import _normalize_expiry as _norm_exp
                            # Load wizard defaults from repo memory if present
                            _prefs_mem = {}
                            try:
                                import json as _json
                                from pathlib import Path as _Path
                                p = _Path(".codex/memory.json")
                                if p.exists():
                                    _data = _json.loads(p.read_text())
                                    _prefs_mem = (
                                        _data.get("preferences", {}).get("order_builder_wizard", {})
                                        or {}
                                    )
                            except Exception:
                                _prefs_mem = {}

                            profile_def = str(_prefs_mem.get("profile", "balanced")).lower()
                            profile = (
                                core_ui.prompt_input(
                                    f"Profile (conservative/balanced/aggressive) [{profile_def}]: "
                                )
                                .strip()
                                .lower()
                                or profile_def
                            )
                            avoid_def = "Y" if bool(_prefs_mem.get("avoid_earnings", True)) else "N"
                            avoid_e = (
                                core_ui.prompt_input(
                                    f"Avoid earnings within 7 days? (Y/n) [{avoid_def}]: "
                                )
                                .strip()
                                .lower()
                            )
                            avoid_e_bool = (avoid_e in {"", "y"})
                            # Liquidity thresholds (prefilled)
                            min_oi_def = str(_prefs_mem.get("min_oi", 200))
                            min_volume_def = str(_prefs_mem.get("min_volume", 50))
                            max_spread_def = str(_prefs_mem.get("max_spread_pct", 0.02))
                            min_oi_in = core_ui.prompt_input(f"Min OI [{min_oi_def}]: ").strip() or min_oi_def
                            min_vol_in = core_ui.prompt_input(f"Min Volume [{min_volume_def}]: ").strip() or min_volume_def
                            max_spread_in = core_ui.prompt_input(
                                f"Max spread fraction of mid [{max_spread_def}]: "
                            ).strip() or max_spread_def
                            try:
                                rules = LiquidityRules(
                                    min_oi=int(min_oi_in),
                                    min_volume=int(min_vol_in),
                                    max_spread_pct=float(max_spread_in),
                                )
                            except Exception:
                                rules = LiquidityRules()
                            # Support DTE entry as number as well as expiry text
                            dte_or_exp = expiry
                            if dte_or_exp.isdigit():
                                import datetime as _dt
                                d = _dt.date.today() + _dt.timedelta(days=int(dte_or_exp))
                                expiry = d.isoformat()
                            expiry = _norm_exp(symbol, expiry)
                            # Include risk budget pct for suggested qty
                            rb_def_val = _prefs_mem.get("risk_budget_pct", 2)
                            rb_def = str(rb_def_val)
                            rb = core_ui.prompt_input(
                                f"Risk budget % of NetLiq for sizing [{rb_def}]: "
                            ).strip() or rb_def
                            try:
                                rb_pct = float(rb) / 100.0
                            except Exception:
                                rb_pct = None
                            # Additional prompts for right where needed
                            right = None
                            if preset in {"butterfly", "calendar"}:
                                right_in = core_ui.prompt_input("Right (C/P) [C]: ").strip().upper() or "C"
                                right = "C" if right_in != "P" else "P"

                            if preset in {"bull_put", "bear_call"}:
                                cands = suggest_credit_vertical(
                                    symbol,
                                    expiry,
                                    preset,
                                    profile,
                                    avoid_earnings=avoid_e_bool,
                                    earnings_window_days=7,
                                    risk_budget_pct=rb_pct,
                                    rules=rules,
                                )
                            elif preset in {"bull_call", "bear_put"}:
                                cands = suggest_debit_vertical(
                                    symbol,
                                    expiry,
                                    preset,
                                    profile,
                                    avoid_earnings=avoid_e_bool,
                                    earnings_window_days=7,
                                    rules=rules,
                                )
                            elif preset in {"iron_condor"}:
                                cands = suggest_iron_condor(
                                    symbol,
                                    expiry,
                                    profile,
                                    avoid_earnings=avoid_e_bool,
                                    earnings_window_days=7,
                                    risk_budget_pct=rb_pct,
                                    rules=rules,
                                )
                            elif preset in {"butterfly"}:
                                # Right is required for butterfly auto
                                cands = suggest_butterfly(
                                    symbol,
                                    expiry,
                                    right or "C",
                                    profile,
                                    avoid_earnings=avoid_e_bool,
                                    earnings_window_days=7,
                                    rules=rules,
                                )
                            else:  # calendar
                                # Ask optional diagonal offset steps (0 = calendar)
                                so = core_ui.prompt_input("Diagonal far strike offset steps (0=calendar) [0]: ").strip()
                                try:
                                    strike_offset = int(so) if so else 0
                                except Exception:
                                    strike_offset = 0
                                cands = suggest_calendar(
                                    symbol,
                                    expiry,
                                    right or "C",
                                    profile,
                                    avoid_earnings=avoid_e_bool,
                                    earnings_window_days=7,
                                    rules=rules,
                                    strike_offset=strike_offset,
                                )
                            if not cands:
                                console.print("[yellow]No candidates met liquidity/selection criteria; falling back to manual width.[/yellow]")
                            else:
                                resolved_exp = cands[0].get("expiry", expiry)
                                tbl = Table(title=f"{preset} candidates ({symbol} {resolved_exp})")
                                tbl.add_column("#", justify="right")
                                tbl.add_column("Strikes", justify="left")
                                tbl.add_column("Type", justify="center")
                                tbl.add_column("Price", justify="right")
                                tbl.add_column("Width", justify="right")
                                tbl.add_column("Risk", justify="right")
                                tbl.add_column("POP", justify="right")
                                tbl.add_column("Qty*", justify="right")
                                for i, c in enumerate(cands, 1):
                                    ks = sorted([leg.get("strike") for leg in c.get("legs", [])])
                                    typ = "CR" if "credit" in c else ("DR" if "debit" in c else "CR")
                                    price = c.get("credit", c.get("debit", 0.0))
                                    risk = c.get("max_loss", c.get("debit", 0.0))
                                    # Annotate calendar near/far and diagonal offset succinctly
                                    strikes_txt = ",".join(f"{k:g}" for k in ks)
                                    if preset == "calendar":
                                        try:
                                            sn = c.get("strike_near", ks[0] if ks else "")
                                            sf = c.get("strike_far", ks[-1] if ks else "")
                                            strikes_txt = f"{sn:g}/{sf:g}"
                                        except Exception:
                                            pass
                                        # near/far DTE hint
                                        nf_hint = ""
                                        try:
                                            import datetime as _dt
                                            n = c.get("near") or (c.get("legs", [{}])[0].get("expiry"))
                                            f = c.get("far") or c.get("expiry")
                                            if n and f:
                                                dn = max(0, ( _dt.date.fromisoformat(str(n)) - _dt.date.today()).days )
                                                df = max(0, ( _dt.date.fromisoformat(str(f)) - _dt.date.today()).days )
                                                nf_hint = f"n/f {dn}/{df}"
                                        except Exception:
                                            nf_hint = ""
                                        # diagonal offset hint using the offset we asked for
                                        diag_hint = ""
                                        try:
                                            if 'strike_offset' in locals():
                                                off = int(strike_offset)
                                            else:
                                                off = 0
                                            if off:
                                                sgn = "+" if (right or "C") == "C" else "-"
                                                diag_hint = f"Δ{sgn}{abs(off)}"
                                        except Exception:
                                            diag_hint = ""
                                        extras = ", ".join([t for t in (nf_hint, diag_hint) if t])
                                        if extras:
                                            strikes_txt = f"{strikes_txt} ({extras})"
                                    tbl.add_row(
                                        str(i),
                                        strikes_txt,
                                        typ,
                                        f"{price:.2f}",
                                        f"{c.get('width',0):.2f}",
                                        f"{risk:.2f}",
                                        f"{c.get('pop_proxy',0):.2f}",
                                        str(c.get('suggested_qty','')),
                                    )
                                console.print(tbl)
                                sel = core_ui.prompt_input("Select candidate # (or Enter to skip): ").strip()
                                if sel.isdigit() and 1 <= int(sel) <= len(cands):
                                    pick = cands[int(sel) - 1]
                                    ks = [leg.get("strike") for leg in pick.get("legs", [])]
                                    expiry = pick.get("expiry", expiry)
                                    # Suggested qty handling if user asked for auto previously
                                    eff_qty = qty
                                    if (qty.strip().lower() in {"", "a", "auto"}) and pick.get("suggested_qty"):
                                        eff_qty = str(int(pick.get("suggested_qty")))
                                        use_auto = core_ui.prompt_input(f"Use suggested qty {eff_qty}? (Y/n) [Y]: ").strip().lower()
                                        if use_auto == "n":
                                            eff_qty = core_ui.prompt_input("Qty: ").strip() or eff_qty
                                    # Build via strategy based on preset
                                    if preset in {"bull_put"} and len(ks)>=2:
                                        args = [
                                            "--strategy", "vertical",
                                            "--symbol", symbol,
                                            "--expiry", expiry,
                                            "--right", "P",
                                            "--credit",
                                            "--strikes", f"{ks[0]},{ks[1]}",
                                            "--qty", eff_qty,
                                            "--json", "--no-files",
                                        ]
                                    elif preset in {"bull_call"} and len(ks)>=2:
                                        args = [
                                            "--strategy", "vertical",
                                            "--symbol", symbol,
                                            "--expiry", expiry,
                                            "--right", "C",
                                            "--debit",
                                            "--strikes", f"{ks[0]},{ks[1]}",
                                            "--qty", eff_qty,
                                            "--json", "--no-files",
                                        ]
                                    elif preset in {"bear_put"} and len(ks)>=2:
                                        args = [
                                            "--strategy", "vertical",
                                            "--symbol", symbol,
                                            "--expiry", expiry,
                                            "--right", "P",
                                            "--debit",
                                            "--strikes", f"{ks[0]},{ks[1]}",
                                            "--qty", eff_qty,
                                            "--json", "--no-files",
                                        ]
                                    elif preset in {"iron_condor"} and len(ks)>=4:
                                        args = [
                                            "--strategy", "iron_condor",
                                            "--symbol", symbol,
                                            "--expiry", expiry,
                                            "--strikes", ",".join(str(k) for k in sorted(ks)),
                                            "--qty", eff_qty,
                                            "--json", "--no-files",
                                        ]
                                    
                                    elif preset in {"butterfly"} and len(ks)>=3:
                                        # Build butterfly with selected right
                                        args = [
                                            "--strategy", "butterfly",
                                            "--symbol", symbol,
                                            "--expiry", expiry,
                                            "--right", (right or "C"),
                                            "--strikes", ",".join(str(k) for k in sorted(ks)[:3]),
                                            "--qty", eff_qty,
                                            "--json", "--no-files",
                                        ]
                                    elif preset in {"calendar"} and len(ks)>=1:
                                        # Prefer wizard pick to support diagonal if strikes differ
                                        near = pick.get("near") or pick.get("legs", [{}])[0].get("expiry")
                                        far = pick.get("far") or pick.get("expiry", expiry)
                                        # Use wizard auto pick path to emit consistent ticket JSON
                                        args = [
                                            "--wizard", "--auto",
                                            "--strategy", "calendar",
                                            "--right", (right or "C"),
                                            "--symbol", symbol,
                                            "--expiry", expiry,
                                            "--pick", str(int(sel)),
                                            "--json", "--no-files",
                                        ]
                                    else:
                                        console.print("[yellow]Automatic ticket build not supported for this selection; please use manual.")
                                        continue
                                    buf = io.StringIO()
                                    with contextlib.redirect_stdout(buf):
                                        _ob.cli(args)
                                    try:
                                        summary = json.loads(buf.getvalue())
                                    except Exception:
                                        console.print("[red]Builder failed[/red]")
                                        continue
                                    ticket = summary.get("ticket")
                                    risk = summary.get("risk_summary")
                                    console.print(ticket)
                                    if risk:
                                        console.print(risk)
                                    if ticket:
                                        save = core_ui.prompt_input("Save ticket? (Y/n) [Y]: ").strip().lower()
                                        if save in {"", "y"}:
                                            io_save(ticket, "order_ticket", fmt="json")
                                            # Copy JSON to clipboard in interactive mode
                                            if os.getenv("PE_QUIET") in (None, "", "0"):
                                                try:
                                                    if _copy_to_clipboard(json.dumps(ticket, separators=(",", ":"))):
                                                        console.print("Copied ticket JSON to clipboard")
                                                except Exception:
                                                    pass
                                    # Continue to next loop
                                    continue
                    args = [
                        "--preset",
                        preset,
                        "--symbol",
                        symbol,
                        "--expiry",
                        expiry,
                        "--qty",
                        qty,
                        "--json",
                        "--no-files",
                    ]
                    if preset in {"bull_put", "bear_call", "bull_call", "bear_put"}:
                        width = core_ui.prompt_input("Width [5]: ").strip() or "5"
                        args.extend(["--width", width])
                    elif preset in {"iron_condor", "iron_fly"}:
                        wings = core_ui.prompt_input("Wings [5]: ").strip() or "5"
                        args.extend(["--wings", wings])
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf):
                        _ob.cli(args)
                    try:
                        summary = json.loads(buf.getvalue())
                    except Exception:
                        console.print("[red]Builder failed[/red]")
                        continue
                    ticket = summary.get("ticket")
                    risk = summary.get("risk_summary")
                    console.print(ticket)
                    if risk:
                        console.print(risk)
                    if ticket:
                        save = core_ui.prompt_input("Save ticket? (Y/n) [Y]: ").strip().lower()
                        if save in {"", "y"}:
                            io_save(ticket, "order_ticket", fmt="json")

            def _roll_positions() -> None:
                from portfolio_exporter.scripts import roll_manager as _rm

                _rm.run()

            def _quick_chain() -> None:
                from portfolio_exporter.scripts import option_chain_snapshot as _ocs

                _ocs.run(fmt=current_fmt)

            def _net_liq() -> None:
                from portfolio_exporter.scripts import net_liq_history_export as _netliq

                _netliq.main(["--quiet", "--no-pretty"] if os.getenv("PE_QUIET") else [])

            def _generate_daily_report() -> None:
                from portfolio_exporter.scripts import daily_report as _daily

                fmt_flag = {"pdf": "--pdf", "excel": "--excel"}.get(current_fmt, "--html")
                args = [fmt_flag]
                if os.getenv("PE_QUIET"):
                    args.append("--no-pretty")
                summary = _daily.main(args)
                # Print where files were written (paths list in summary.outputs)
                try:
                    outs = summary.get("outputs", []) if isinstance(summary, dict) else []
                    if outs:
                        # Show last written artifact path for convenience
                        console.print(outs[-1])
                except Exception:
                    pass
                # Offer to open the last report immediately
                quiet = os.getenv("PE_QUIET") not in (None, "", "0")
                ch = core_ui.prompt_input("Open last report now? (Y/n) [Y]: ").strip().lower()
                if ch in {"", "y"}:
                    msg = open_last_report(quiet=quiet)
                    console.print(msg)

            def _open_last() -> None:
                quiet = os.getenv("PE_QUIET") not in (None, "", "0")
                msg = open_last_report(quiet=quiet)
                console.print(msg)

            def _open_last_ticket() -> None:
                from portfolio_exporter.core.io import latest_file
                quiet = os.getenv("PE_QUIET") not in (None, "", "0")
                path = latest_file("order_ticket", "json")
                if not path:
                    console.print("[yellow]No order ticket found")
                    return
                try:
                    txt = Path(path).read_text()
                except Exception:
                    txt = ""
                print(path)
                if not quiet and txt:
                    if _copy_to_clipboard(txt):
                        console.print("Copied ticket JSON to clipboard")

            def _save_filtered() -> None:
                quiet = os.getenv("PE_QUIET") not in (None, "", "0")
                from portfolio_exporter.core.config import settings
                # Prefill from Pre-Market cache and memory
                try:
                    from portfolio_exporter.menus import pre as _pre_menu
                    _last_sym = _pre_menu.last_symbol.get()
                except Exception:
                    _last_sym = ""
                # Load memory preferences
                _mem = {}
                try:
                    from pathlib import Path as _Path
                    _p = _Path(".codex/memory.json")
                    if _p.exists():
                        _mem = json.loads(_p.read_text()).get("preferences", {}).get("trades_filters", {})
                except Exception:
                    _mem = {}
                defv_sym = _mem.get("symbols", _last_sym)
                defv_eff = _mem.get("effect") or ""
                defv_str = _mem.get("structure") or ""
                defv_top = str(_mem.get("top_n", "")) if _mem.get("top_n") is not None else ""

                symbols = (core_ui.prompt_input(f"Symbols (comma-separated) [{defv_sym}]: ").strip() or defv_sym) or None
                effect = (core_ui.prompt_input(f"Effect (Open/Close/Roll) [{defv_eff}]: ").strip() or defv_eff) or None
                structure = (core_ui.prompt_input(f"Structure (e.g., vertical, iron_condor) [{defv_str}]: ").strip() or defv_str) or None
                top_n = core_ui.prompt_input(f"Top N (optional) [{defv_top}]: ").strip() or defv_top
                top = int(top_n) if str(top_n).strip().isdigit() else None
                summary = _quick_save_filtered(
                    output_dir=str(settings.output_dir),
                    symbols=symbols,
                    effect_in=effect,
                    structure_in=structure,
                    top_n=top,
                    quiet=quiet,
                )
                # Clipboard: copy last output path if available
                try:
                    outs = [str(p) for p in summary.get("outputs", []) if p]
                    if outs:
                        last = outs[-1]
                        if not quiet and _copy_to_clipboard(last):
                            console.print("Copied path to clipboard")
                except Exception:
                    pass
                # Persist prefs back to memory (best effort, atomic replace)
                try:
                    from pathlib import Path as _Path
                    _pf = _Path(".codex/memory.json")
                    data = {}
                    if _pf.exists():
                        data = json.loads(_pf.read_text())
                    prefs = data.setdefault("preferences", {})
                    prefs["trades_filters"] = {
                        "symbols": symbols or "",
                        "effect": effect or "",
                        "structure": structure or "",
                        "top_n": top if top is not None else "",
                    }
                    tmp = _pf.with_suffix(".json.tmp")
                    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
                    os.replace(tmp, _pf)
                except Exception:
                    pass

            def _copy_trades_json() -> None:
                quiet = os.getenv("PE_QUIET") not in (None, "", "0")
                # Prefill from memory and Pre menu
                try:
                    from portfolio_exporter.menus import pre as _pre_menu
                    _last_sym = _pre_menu.last_symbol.get()
                except Exception:
                    _last_sym = ""
                _mem = {}
                try:
                    from pathlib import Path as _Path
                    _p = _Path(".codex/memory.json")
                    if _p.exists():
                        _mem = json.loads(_p.read_text()).get("preferences", {}).get("trades_filters", {})
                except Exception:
                    _mem = {}
                defv_sym = _mem.get("symbols", _last_sym)
                defv_eff = _mem.get("effect") or ""
                defv_str = _mem.get("structure") or ""
                defv_top = str(_mem.get("top_n", "")) if _mem.get("top_n") is not None else ""

                symbols = (core_ui.prompt_input(f"Symbols (comma-separated) [{defv_sym}]: ").strip() or defv_sym) or None
                effect = (core_ui.prompt_input(f"Effect (Open/Close/Roll) [{defv_eff}]: ").strip() or defv_eff) or None
                structure = (core_ui.prompt_input(f"Structure (e.g., vertical, iron_condor) [{defv_str}]: ").strip() or defv_str) or None
                top_n = core_ui.prompt_input(f"Top N (optional) [{defv_top}]: ").strip() or defv_top
                top = int(top_n) if str(top_n).strip().isdigit() else None
                txt = _preview_trades_json(symbols=symbols, effect_in=effect, structure_in=structure, top_n=top)
                if quiet:
                    import tempfile

                    p = Path(tempfile.gettempdir()) / "trades_summary.json"
                    p.write_text(txt)
                    console.print(p)
                else:
                    if _copy_to_clipboard(txt):
                        console.print("Copied summary to clipboard")
                    else:
                        console.print(txt)
                # Persist selections
                try:
                    from pathlib import Path as _Path
                    _pf = _Path(".codex/memory.json")
                    data = {}
                    if _pf.exists():
                        data = json.loads(_pf.read_text())
                    prefs = data.setdefault("preferences", {})
                    prefs["trades_filters"] = {
                        "symbols": symbols or "",
                        "effect": effect or "",
                        "structure": structure or "",
                        "top_n": top if top is not None else "",
                    }
                    tmp = _pf.with_suffix(".json.tmp")
                    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
                    os.replace(tmp, _pf)
                except Exception:
                    pass

            def _preview_combos_mtm() -> None:
                """Compute MTM P&L for detected combos using mid quotes; JSON-only."""
                from portfolio_exporter.scripts import trades_report as _tr
                from portfolio_exporter.core.ib import quote_option, quote_stock
                import time as _time
                try:
                    execs = session.get("execs_df")
                    if execs is None or not hasattr(execs, "empty"):
                        execs = _tr._load_trades()
                except Exception as exc:
                    console.print(f"[red]Failed to load executions:[/] {exc}")
                    return
                try:
                    opens = _tr._load_open_orders()
                except Exception:
                    opens = None
                try:
                    combos = session.get("combos_df")
                    pos_like = session.get("pos_like_df")
                    if combos is None:
                        combos = _tr._detect_and_enrich_trades_combos(execs, opens, prev_positions_df=None)
                    if pos_like is None:
                        pos_like = _tr._build_positions_like_df(execs, opens)
                except Exception as exc:
                    console.print(f"[red]Failed to detect combos:[/] {exc}")
                    return
                if combos is None or len(combos) == 0:
                    console.print("[yellow]No combos detected for the selected range.")
                    return
                # Build conId -> attrs map
                import pandas as _pd
                id_map = {}
                try:
                    p = pos_like.copy()
                    for c in ("conId","strike","qty","multiplier"):
                        if c in p.columns:
                            p[c] = _pd.to_numeric(p[c], errors="coerce")
                    if "right" in p.columns:
                        p["right"] = p["right"].astype(str).str.upper()
                    if "underlying" in p.columns:
                        p["underlying"] = p["underlying"].astype(str).str.upper()
                    if "expiry" in p.columns:
                        p["expiry"] = _pd.to_datetime(p["expiry"], errors="coerce").dt.date.astype(str)
                    for _, r in p.iterrows():
                        cid = r.get("conId")
                        if _pd.isna(cid):
                            continue
                        id_map[int(cid)] = {
                            "underlying": r.get("underlying"),
                            "expiry": r.get("expiry"),
                            "right": r.get("right"),
                            "strike": float(r.get("strike")) if _pd.notna(r.get("strike")) else None,
                            "qty": float(r.get("qty", 0.0) or 0.0),
                            "mult": int(r.get("multiplier", 100) or 100),
                        }
                except Exception:
                    pass
                import ast
                rows: list[dict] = []
                # Lightweight in-memory quote cache with TTL and overall budget
                _qcache: dict[tuple, tuple[float, float]] = {}
                _TTL_SEC = 30.0
                _BUDGET_SEC = 8.0
                _t0 = _time.time()

                def _get_mid(sym: str, exp: str | None, strike: float | None, right: str | None) -> float | None:
                    now = _time.time()
                    if now - _t0 > _BUDGET_SEC:
                        return None
                    key = (sym, exp or "", float(strike) if strike is not None else float("nan"), (right or "").upper())
                    hit = _qcache.get(key)
                    if hit and (now - hit[0] <= _TTL_SEC):
                        return hit[1]
                    mid = None
                    try:
                        if right in {"C", "P"} and exp and strike is not None:
                            q = quote_option(sym, exp, float(strike), right)
                            mid = float(q.get("mid")) if q and q.get("mid") is not None else None
                        else:
                            q = quote_stock(sym)
                            mid = float(q.get("mid")) if q and q.get("mid") is not None else None
                    except Exception:
                        mid = None
                    # cache even None with timestamp to avoid hammering
                    _qcache[key] = (now, mid if mid is not None else float("nan"))
                    return mid
                for _, row in combos.iterrows():
                    legs_val = row.get("legs")
                    try:
                        leg_ids = ast.literal_eval(legs_val) if isinstance(legs_val, str) else (legs_val or [])
                    except Exception:
                        leg_ids = []
                    net_cd = float(row.get("net_credit_debit", 0.0) or 0.0)
                    cur_val = 0.0
                    quoted = 0
                    total_legs = len(leg_ids or [])
                    for cid in (leg_ids or []):
                        attrs = id_map.get(int(cid))
                        if not attrs:
                            continue
                        sym = attrs.get("underlying")
                        qty = float(attrs.get("qty", 0.0) or 0.0)
                        mult = int(attrs.get("mult", 100) or 100)
                        mid = _get_mid(sym, attrs.get("expiry"), attrs.get("strike"), attrs.get("right"))
                        if mid is None:
                            continue
                        cur_val += mid * qty * mult
                        quoted += 1
                    mtm = net_cd - cur_val
                    rows.append({
                        "underlying": row.get("underlying"),
                        "structure": row.get("structure"),
                        "legs_n": int(row.get("legs_n", 0) or 0),
                        "net_credit_debit": net_cd,
                        "current_value": cur_val,
                        "mtm_pnl": mtm,
                        "quoted_legs": quoted,
                        "total_legs": total_legs,
                        "quoted_ratio": (f"{quoted}/{total_legs}" if total_legs else "0/0"),
                        "when": str(row.get("when")),
                    })
                out = {"ok": True, "combos_mtm": rows, "meta": {"schema_id": "combos_mtm_preview", "schema_version": "1"}}
                txt = json.dumps(out, separators=(",", ":"))
                if os.getenv("PE_QUIET") not in (None, "", "0"):
                    console.print(txt)
                else:
                    if _copy_to_clipboard(txt):
                        console.print("Copied MTM combos JSON to clipboard")
                    else:
                        console.print(txt)

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
                "o": _open_last,
                "k": _open_last_ticket,
                "s": _save_filtered,
                "j": _copy_trades_json,
                "m": _preview_combos_mtm,
                "t": None,
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
            elif ch == "t":
                order = ["csv", "excel", "pdf"]
                try:
                    idx = order.index(current_fmt)
                except ValueError:
                    idx = 0
                current_fmt = order[(idx + 1) % len(order)]
