from __future__ import annotations

from __future__ import annotations

import builtins as _builtins
import os
from contextlib import contextmanager
from pathlib import Path

import json

from rich.console import Console
from rich.table import Table

from portfolio_exporter.core.ui import prompt_input
import datetime as _dt


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
    if symbols:
        argv.extend(["--symbol", symbols])
    if effect_in:
        argv.extend(["--effect-in", effect_in])
    if structure_in:
        argv.extend(["--structure-in", structure_in])
    if top_n is not None:
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
    if symbols:
        argv.extend(["--symbol", symbols])
    if effect_in:
        argv.extend(["--effect-in", effect_in])
    if structure_in:
        argv.extend(["--structure-in", structure_in])
    if top_n is not None:
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
            if not summary.get("warnings"):
                console.print("Preflight OK: files can be generated.")
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
            ("s", "Save filtered trades CSV… (choose filters)"),
            ("j", "Copy trades JSON summary (filtered)"),
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
                from portfolio_exporter.core.io import save as io_save
                import json, io, contextlib

                while True:
                    tbl = Table(title="Stage Order")
                    opts = [("p", "Preset"), ("w", "Wizard"), ("r", "Return")]
                    for k, lbl in opts:
                        tbl.add_row(k, lbl)
                    console.print(tbl)
                    ch = prompt_input("› ").strip().lower()
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
                    sel = prompt_input("Preset #: ").strip()
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
                    symbol = (prompt_input(sym_prompt).strip().upper() or _last_sym).upper()
                    expiry = prompt_input(exp_prompt).strip() or _last_exp
                    # Update last symbol/expiry cache
                    try:
                        if symbol:
                            _pre_menu.last_symbol.value = symbol
                        if expiry:
                            _pre_menu.last_expiry.value = expiry
                    except Exception:
                        pass
                    qty = prompt_input("Qty [1]: ").strip() or "1"

                    # Optional: auto-select strikes for supported presets using live data
                    if preset in {"bull_put", "bear_call", "bull_call", "bear_put", "iron_condor", "butterfly", "calendar"}:
                        auto = prompt_input("Auto-select strikes from live data? (Y/n) [Y]: ").strip().lower()
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
                                prompt_input(
                                    f"Profile (conservative/balanced/aggressive) [{profile_def}]: "
                                )
                                .strip()
                                .lower()
                                or profile_def
                            )
                            avoid_def = "Y" if bool(_prefs_mem.get("avoid_earnings", True)) else "N"
                            avoid_e = (
                                prompt_input(
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
                            min_oi_in = prompt_input(f"Min OI [{min_oi_def}]: ").strip() or min_oi_def
                            min_vol_in = prompt_input(f"Min Volume [{min_volume_def}]: ").strip() or min_volume_def
                            max_spread_in = prompt_input(
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
                            rb = prompt_input(
                                f"Risk budget % of NetLiq for sizing [{rb_def}]: "
                            ).strip() or rb_def
                            try:
                                rb_pct = float(rb) / 100.0
                            except Exception:
                                rb_pct = None
                            # Additional prompts for right where needed
                            right = None
                            if preset in {"butterfly", "calendar"}:
                                right_in = prompt_input("Right (C/P) [C]: ").strip().upper() or "C"
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
                                so = prompt_input("Diagonal far strike offset steps (0=calendar) [0]: ").strip()
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
                                sel = prompt_input("Select candidate # (or Enter to skip): ").strip()
                                if sel.isdigit() and 1 <= int(sel) <= len(cands):
                                    pick = cands[int(sel) - 1]
                                    ks = [leg.get("strike") for leg in pick.get("legs", [])]
                                    expiry = pick.get("expiry", expiry)
                                    # Suggested qty handling if user asked for auto previously
                                    eff_qty = qty
                                    if (qty.strip().lower() in {"", "a", "auto"}) and pick.get("suggested_qty"):
                                        eff_qty = str(int(pick.get("suggested_qty")))
                                        use_auto = prompt_input(f"Use suggested qty {eff_qty}? (Y/n) [Y]: ").strip().lower()
                                        if use_auto == "n":
                                            eff_qty = prompt_input("Qty: ").strip() or eff_qty
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
                                        save = prompt_input("Save ticket? (Y/n) [Y]: ").strip().lower()
                                        if save in {"", "y"}:
                                            io_save(ticket, "order_ticket", fmt="json")
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
                        width = prompt_input("Width [5]: ").strip() or "5"
                        args.extend(["--width", width])
                    elif preset in {"iron_condor", "iron_fly"}:
                        wings = prompt_input("Wings [5]: ").strip() or "5"
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
                        save = prompt_input("Save ticket? (Y/n) [Y]: ").strip().lower()
                        if save in {"", "y"}:
                            io_save(ticket, "order_ticket", fmt="json")

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
                # Offer to open the last report immediately
                quiet = os.getenv("PE_QUIET") not in (None, "", "0")
                ch = prompt_input("Open last report now? (Y/n) [Y]: ").strip().lower()
                if ch in {"", "y"}:
                    msg = open_last_report(quiet=quiet)
                    console.print(msg)

            def _open_last() -> None:
                quiet = os.getenv("PE_QUIET") not in (None, "", "0")
                msg = open_last_report(quiet=quiet)
                console.print(msg)

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

                symbols = (prompt_input(f"Symbols (comma-separated) [{defv_sym}]: ").strip() or defv_sym) or None
                effect = (prompt_input(f"Effect (Open/Close/Roll) [{defv_eff}]: ").strip() or defv_eff) or None
                structure = (prompt_input(f"Structure (e.g., vertical, iron_condor) [{defv_str}]: ").strip() or defv_str) or None
                top_n = prompt_input(f"Top N (optional) [{defv_top}]: ").strip() or defv_top
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

                symbols = (prompt_input(f"Symbols (comma-separated) [{defv_sym}]: ").strip() or defv_sym) or None
                effect = (prompt_input(f"Effect (Open/Close/Roll) [{defv_eff}]: ").strip() or defv_eff) or None
                structure = (prompt_input(f"Structure (e.g., vertical, iron_condor) [{defv_str}]: ").strip() or defv_str) or None
                top_n = prompt_input(f"Top N (optional) [{defv_top}]: ").strip() or defv_top
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
                "s": _save_filtered,
                "j": _copy_trades_json,
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
