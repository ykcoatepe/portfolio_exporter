from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

try:
    import dateparser  # type: ignore
except Exception:  # minimal fallback to avoid hard dependency in tests
    from datetime import datetime as _dt

    class _DP:  # type: ignore
        @staticmethod
        def parse(s, settings=None):
            try:
                return _dt.fromisoformat(str(s))
            except Exception:
                return None

    dateparser = _DP()  # type: ignore
import pandas as pd
from rich.console import Console
from rich.live import Live
from rich.table import Table

from portfolio_exporter.core import chain as core_chain
from portfolio_exporter.core import cli as cli_helpers
from portfolio_exporter.core import json as json_helpers
from portfolio_exporter.core import ui as core_ui
from portfolio_exporter.core.config import settings
from portfolio_exporter.core.io import save as io_save
from portfolio_exporter.core.runlog import RunLog

render_chain = core_ui.render_chain
run_with_spinner = core_ui.run_with_spinner


def _calc_strikes(symbol: str, width: int) -> list[float]:
    """Return a list of strikes around ATM using 5-point increments."""
    try:
        from portfolio_exporter.core.ib import quote_stock

        spot = quote_stock(symbol)["mid"]
    except Exception:
        spot = 0
    return [round((spot // 5 + i) * 5, 0) for i in range(-width, width + 1)]


def run(
    symbol: str | None = None,
    expiry: str | None = None,
    strikes: list[float] | None = None,
    width: int = 5,
) -> None:
    """Interactive Rich-based option-chain browser with natural-language expiry parsing."""

    from portfolio_exporter.menus import pre as pre_menu

    console = Console()

    default_symbol = symbol or pre_menu.last_symbol.get()
    # ─────────────────── input & defaults ────────────────────────────
    symbol = input(f"Symbol [{default_symbol}]: ").strip().upper() or default_symbol
    if not symbol:
        return
    pre_menu.last_symbol.value = symbol

    default_expiry = expiry or pre_menu.last_expiry.get()
    normalize_exps = expiry is None
    # ── natural‑language expiry parsing ──────────────────────────────
    if not expiry:
        exp_raw = (
            input(f"Expiry (YYYY-MM-DD, 'Aug 15', '+30d', etc.) [{default_expiry}]: ").strip()
            or default_expiry
        )
    else:
        exp_raw = expiry
    parsed_exp = dateparser.parse(exp_raw, settings={"PREFER_DATES_FROM": "future"})
    if not parsed_exp:
        console.print(f"[red]Could not parse expiry '{exp_raw}'.")
        return
    expiry = parsed_exp.strftime("%Y-%m-%d")
    pre_menu.last_expiry.value = expiry

    from yfinance import Ticker

    all_exps: list[str] = []

    def _valid_expirations(sym: str) -> list[str]:
        nonlocal all_exps
        if all_exps:
            return all_exps
        try:
            all_exps = Ticker(sym).options
        except Exception:
            # Network unavailable; skip normalization
            all_exps = []
        return all_exps

    def _nearest(expiry_date: str) -> str:
        # if the requested expiry is not listed, pick the next later one
        exps = _valid_expirations(symbol)
        if not exps:
            return expiry_date
        if expiry_date in exps:
            return expiry_date
        for e in exps:
            if e > expiry_date:
                return e
        return exps[-1]  # fallback: last available

    # ------------- CSV toggle (default = ON) -------------------------
    save_csv_env = os.getenv("PE_CHAIN_CSV", "1")  # allow override
    # In tests, default to no CSV unless explicitly forced on
    if os.getenv("PYTEST_CURRENT_TEST") and save_csv_env == "1":
        save_csv_env = "0"
    save_csv = save_csv_env.lower() not in {"0", "false", "no"}

    def _fetch(cur_width: int, cur_expiry: str) -> pd.DataFrame:
        exp = _nearest(cur_expiry) if normalize_exps else cur_expiry
        use_strikes = strikes if strikes is not None else _calc_strikes(symbol, cur_width)
        df = run_with_spinner(
            f"Fetching {symbol} {exp} …",
            core_chain.fetch_chain,
            symbol,
            exp,
            use_strikes,
        )
        # ── optional CSV export ──────────────────────────────────────
        if save_csv:
            # Same directory convention as the other scripts
            out_dir = os.getenv("PE_OUTPUT_DIR", settings.output_dir)
            os.makedirs(out_dir, exist_ok=True)
            csv_path = os.path.join(out_dir, f"chain_{symbol}_{exp.replace('-', '')}.csv")
            df.to_csv(csv_path, index=False)
            console.print(f"[green]CSV saved → {csv_path}")
        return df

    df = _fetch(width, expiry)

    def _grid() -> Table:
        calls = df[df["right"] == "C"].sort_values("strike").reset_index(drop=True)
        puts = df[df["right"] == "P"].sort_values("strike").reset_index(drop=True)
        grid = Table.grid(expand=True)
        grid.add_row(render_chain(calls, console, width), render_chain(puts, console, width))
        return grid

    interactive = sys.stdin.isatty() or bool(os.environ.get("PYTEST_CURRENT_TEST"))
    if not interactive:
        console.print(_grid())
        return

    # ----------- interactive loop (render + hot-keys) ----------------
    toggle_msg = "[yellow]↑/↓: navigate  [cyan]space[/cyan]: mark  [cyan]b[/cyan]: build  [cyan]c[/cyan]: toggle CSV export  [cyan]q[/cyan]: quit"
    console.print(toggle_msg)

    cursor = 0
    marked: list[int] = []

    with Live(_grid(), console=console, refresh_per_second=2) as live:
        while True:
            cmd = input()
            if cmd == "c":
                save_csv = not save_csv
                console.print(f"[yellow]CSV export {'ON' if save_csv else 'OFF'}")
                continue
            if cmd == "q":
                break
            if cmd == "\x1b[A":
                cursor = max(0, cursor - 1)
            elif cmd == "\x1b[B":
                cursor = min(len(df) - 1, cursor + 1)
            elif cmd == "[":
                width = max(1, width - 2)
                df = _fetch(width, expiry)
            elif cmd == "]":
                width += 2
                df = _fetch(width, expiry)
            elif cmd == ">":
                expiry = (pd.to_datetime(expiry) + pd.Timedelta(weeks=1)).date().isoformat()
                df = _fetch(width, expiry)
            elif cmd == "<":
                expiry = (pd.to_datetime(expiry) - pd.Timedelta(weeks=1)).date().isoformat()
                df = _fetch(width, expiry)
            elif cmd == " ":
                if cursor not in marked:
                    marked.append(cursor)
            elif cmd == "b" and len(marked) >= 2:
                from portfolio_exporter.scripts import order_builder

                order_builder.run()
                marked.clear()
            live.update(_grid())


# ───────────────────────────── V3 CLI (additive) ─────────────────────────────
def _is_third_friday(d: date) -> bool:
    # 3rd Friday: weekday() == 4 (Mon=0..Sun=6) and day in 15..21
    return d.weekday() == 4 and 15 <= d.day <= 21


def _classify_tenor(expiry_str: str) -> Literal["weekly", "monthly"] | None:
    try:
        d = date.fromisoformat(expiry_str)
    except Exception:
        try:
            d = pd.to_datetime(expiry_str, errors="coerce").date()
        except Exception:
            return None
    if d is None:
        return None
    return "monthly" if _is_third_friday(d) else "weekly"


def _norm_delta(x: float) -> float:
    try:
        if x is None:
            return float("nan")
        xv = float(x)
        # Heuristic: if magnitude > 1, assume percent-style (×100)
        if abs(xv) > 1.0:
            xv = xv / 100.0
        return xv
    except Exception:
        return float("nan")


def _ensure_delta(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure a usable 'delta' column exists and normalized to [-1,1]."""
    if df is None or df.empty:
        return df
    d = df.copy()
    if "delta" not in d.columns:
        d["delta"] = pd.NA
    d["delta"] = d["delta"].apply(_norm_delta)
    # Best-effort BS fallback if IV and last/mid are present
    missing = d["delta"].isna() | (~d["delta"].apply(lambda v: isinstance(v, (int, float))))
    if missing.any():
        try:
            from portfolio_exporter.core.greeks import bs_greeks

            # Compute t in years based on expiry vs today
            def _row_delta(row) -> float:
                try:
                    exp = date.fromisoformat(str(row.get("expiry")))
                except Exception:
                    return float("nan")
                t = max((exp - date.today()).days, 1) / 365.0
                spot = row.get("last")
                if pd.isna(spot) or not spot:
                    spot = row.get("mid")
                if pd.isna(spot) or not spot:
                    return float("nan")
                strike = float(row.get("strike"))
                iv = row.get("iv")
                if pd.isna(iv) or not iv:
                    return float("nan")
                g = bs_greeks(
                    float(spot),
                    float(strike),
                    float(t),
                    float(getattr(settings.greeks, "risk_free", 0.0) or 0.0),
                    float(iv),
                    call=str(row.get("right", "C")).upper() == "C",
                    multiplier=1,
                )
                return float(g.get("delta", float("nan")))

            calc = d.apply(_row_delta, axis=1)
            d.loc[missing, "delta"] = calc[missing]
        except Exception:
            pass
    # Final normalization in [-1,1]
    d["delta"] = d["delta"].apply(_norm_delta)
    return d


def _same_delta_by_expiry(
    df: pd.DataFrame,
    target: float,
    side: Literal["call", "put", "both"] = "both",
) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    d = _ensure_delta(df)

    # Prepare output columns
    out = d.copy()
    cols = []
    if side in {"call", "both"}:
        cols += [
            "call_same_delta_strike",
            "call_same_delta_delta",
            "call_same_delta_mid",
            "call_same_delta_iv",
        ]
    if side in {"put", "both"}:
        cols += [
            "put_same_delta_strike",
            "put_same_delta_delta",
            "put_same_delta_mid",
            "put_same_delta_iv",
        ]
    for c in cols:
        out[c] = pd.NA

    # Compute nearest picks per expiry and assign to all rows of that expiry
    def _assign_for_exp(expiry: str, g: pd.DataFrame) -> None:
        if side in {"call", "both"}:
            calls = g[g["right"].astype(str).str.upper() == "C"]
            if not calls.empty:
                calls = calls.assign(dist=(calls["delta"] - abs(target)).abs())
                best = calls.loc[calls["dist"].idxmin()]
                out.loc[g.index, "call_same_delta_strike"] = best.get("strike")
                out.loc[g.index, "call_same_delta_delta"] = best.get("delta")
                out.loc[g.index, "call_same_delta_mid"] = (
                    best.get("mid") if "mid" in best else best.get("last")
                )
                out.loc[g.index, "call_same_delta_iv"] = best.get("iv")
        if side in {"put", "both"}:
            puts = g[g["right"].astype(str).str.upper() == "P"]
            if not puts.empty:
                puts = puts.assign(dist=(puts["delta"] - -abs(target)).abs())
                best = puts.loc[puts["dist"].idxmin()]
                out.loc[g.index, "put_same_delta_strike"] = best.get("strike")
                out.loc[g.index, "put_same_delta_delta"] = best.get("delta")
                out.loc[g.index, "put_same_delta_mid"] = (
                    best.get("mid") if "mid" in best else best.get("last")
                )
                out.loc[g.index, "put_same_delta_iv"] = best.get("iv")

    for exp, grp in d.groupby("expiry"):
        _assign_for_exp(str(exp), grp)

    return out


def _filter_tenor(df: pd.DataFrame, tenor: Literal["weekly", "monthly", "all"]) -> pd.DataFrame:
    if df is None or df.empty or tenor == "all":
        return df
    d = df.copy()
    kinds = d["expiry"].astype(str).apply(_classify_tenor)
    if tenor == "monthly":
        return d.loc[kinds == "monthly"].copy()
    else:
        return d.loc[kinds == "weekly"].copy()


def _run_cli_v3() -> int:
    parser = argparse.ArgumentParser(description="Quick-Chain v3: Same-Delta & Tenor Filters")
    parser.add_argument("--chain-csv", help="Offline chain CSV (fixture)", default=None)
    parser.add_argument("--symbols", nargs="*", help="Symbols to fetch (demo)", default=None)
    parser.add_argument("--target-delta", type=float, default=0.30)
    parser.add_argument("--side", choices=["call", "put", "both"], default="both")
    parser.add_argument("--tenor", choices=["weekly", "monthly", "all"], default="all")
    parser.add_argument("--html", action="store_true", default=False)
    parser.add_argument("--pdf", action="store_true", default=False)
    parser.add_argument("--csv", action="store_true", default=False)
    parser.add_argument("--no-pretty", action="store_true", default=False)
    parser.add_argument("--no-files", action="store_true", default=False)
    parser.add_argument("--output-dir", help="Override output directory", default=None)
    parser.add_argument("--json", action="store_true", default=False, help="Emit summary JSON and exit")
    parser.add_argument("--debug-timings", action="store_true")
    args = parser.parse_args()

    formats = cli_helpers.decide_file_writes(
        args,
        json_only_default=True,
        defaults={"csv": bool(args.output_dir), "html": False, "pdf": False},
    )
    outdir = cli_helpers.resolve_output_dir(args.output_dir)
    quiet, pretty = cli_helpers.resolve_quiet(args.no_pretty)

    with RunLog(script="quick_chain", args=vars(args), output_dir=outdir) as rl:
        with rl.time("build"):
            # Build base DataFrame
            df = None
            if args.chain_csv:
                try:
                    df = pd.read_csv(args.chain_csv)
                except Exception as exc:
                    print(f"❌ Failed to read chain CSV: {exc}")
                    return 2
            else:
                # Live/demo path (kept minimal; not used in tests)
                syms = args.symbols or []
                if not syms:
                    print("No symbols provided; nothing to do.")
                    return 1
                frames = []
                for sym in syms:
                    # attempt next available weekly expiry ~30 days from now
                    exp = (date.today() + timedelta(days=30)).isoformat()
                    try:
                        df_sym = core_chain.fetch_chain(sym, exp, strikes=None)
                        df_sym.insert(0, "underlying", sym)
                        df_sym.insert(1, "expiry", exp)
                        frames.append(df_sym)
                    except Exception:
                        continue
                df = pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()

            if df is None or df.empty:
                print("⚠ No chain data available")
                return 0

            # Ensure required columns
            for c in ("underlying", "expiry", "right", "strike"):
                if c not in df.columns:
                    df[c] = pd.NA
            if "mid" not in df.columns:
                if "last" in df.columns:
                    df["mid"] = df["last"]
                else:
                    df["mid"] = pd.NA

            # Tenor filter then same-delta augmentation
            df_f = _filter_tenor(df, args.tenor)
            df_out = _same_delta_by_expiry(df_f, float(args.target_delta), args.side)

        # Outputs
        base_name = "quick_chain"
        outputs = {k: "" for k in formats}
        written: list[Path] = []

        with rl.time("write_outputs"):
            if formats.get("csv"):
                csv_path = io_save(df_out, base_name, fmt="csv", outdir=outdir)
                outputs["csv"] = str(csv_path)
                written.append(csv_path)
                if pretty:
                    Console().print(f"CSV saved → {csv_path}")
                elif not quiet:
                    print(f"CSV saved → {csv_path}")
            if formats.get("html"):
                html_path = io_save(df_out, base_name, fmt="html", outdir=outdir)
                outputs["html"] = str(html_path)
                written.append(html_path)
                if pretty:
                    Console().print(f"HTML saved → {html_path}")
                elif not quiet:
                    print(f"HTML saved → {html_path}")
            if formats.get("pdf"):
                pdf_path = io_save(df_out, base_name, fmt="pdf", outdir=outdir)
                outputs["pdf"] = str(pdf_path)
                written.append(pdf_path)
                if pretty:
                    Console().print(f"PDF saved → {pdf_path}")
                elif not quiet:
                    print(f"PDF saved → {pdf_path}")

            if args.debug_timings:
                if written:
                    tpath = io_save(pd.DataFrame(rl.timings), "timings", fmt="csv", outdir=outdir)
                    outputs["timings"] = str(tpath)
                    written.append(tpath)

        rl.add_outputs(written)
        manifest_path = rl.finalize(write=bool(written))

        meta = {
            "underlyings": [
                str(u) for u in df_out.get("underlying", pd.Series(dtype=str)).dropna().unique().tolist()
            ],
            "tenor": args.tenor or "",
            "target_delta": float(args.target_delta) if args.target_delta is not None else None,
            "side": args.side or "",
        }
        if args.debug_timings:
            meta["timings"] = rl.timings
        summary = json_helpers.report_summary({"chain": int(len(df_out))}, outputs, meta=meta)
        if manifest_path:
            summary["outputs"].append(str(manifest_path))
        if args.json:
            cli_helpers.print_json(summary, quiet)
            return 0

        if sys.stdout.isatty() and pretty:
            Console().print(df_out.head(min(30, len(df_out))))
        elif not quiet:
            print(df_out.head(min(30, len(df_out))).to_string(index=False))
        return 0


def main(argv: list[str] | None = None) -> int:
    if argv is not None:
        import sys

        old = sys.argv
        sys.argv = [sys.argv[0]] + argv
        try:
            return _run_cli_v3()
        finally:
            sys.argv = old
    return _run_cli_v3()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
