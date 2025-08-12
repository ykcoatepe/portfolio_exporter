"""roll_manager.py – helper to roll expiring option combos.

This module provides a small interactive wizard that inspects the current
portfolio, highlights option combos that are close to expiry and helps the user
generate a JSON ticket and CSV preview for rolling those positions.

The implementation in this kata is deliberately lightweight.  Network calls are
wrapped with ``run_with_spinner`` which keeps the behaviour consistent with the
rest of the project while remaining easy to stub in tests.
"""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import pathlib
from typing import List

import pandas as pd
from portfolio_exporter.core import io
from portfolio_exporter.core.combo import detect_combos
from portfolio_exporter.core.chain import fetch_chain
from portfolio_exporter.core.config import settings
from portfolio_exporter.core.ui import run_with_spinner

portfolio_greeks = None  # lazy import to avoid optional deps at module import


def _third_friday(year: int, month: int) -> dt.date:
    """Return the date of the third Friday for ``year``/``month``."""

    cal = calendar.monthcalendar(year, month)
    return dt.date(year, month, cal[2][calendar.FRIDAY])


def _next_expiry(today: dt.date, weekly: bool) -> str:
    """Calculate the next target expiry as ISO date string."""

    if weekly:
        start = today + dt.timedelta(weeks=1)
        while start.weekday() != 4:  # Friday
            start += dt.timedelta(days=1)
        return start.isoformat()

    month = today.month + 1
    year = today.year + (1 if month == 13 else 0)
    month = 1 if month == 13 else month
    exp = _third_friday(year, month)
    if (exp - today).days < 7:
        month += 1
        if month == 13:
            month = 1
            year += 1
        exp = _third_friday(year, month)
    return exp.isoformat()


def _write_files(
    df: pd.DataFrame, pos_df: pd.DataFrame, outdir: str | pathlib.Path | None = None
) -> dict[str, pathlib.Path]:
    """Persist ticket JSON and CSV preview for selected rolls."""

    if df.empty:
        return {}

    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")

    combos_out = []
    for _, row in df.iterrows():
        legs_close = [
            {"conId": int(l), "qty": int(pos_df.loc[l, "qty"])} for l in row.legs_old
        ]
        legs_open = [
            {
                "symbol": row.underlying,
                "expiry": row.new_exp,
                "strike": leg["strike"],
                "right": leg["right"],
                "qty": leg["qty"],
            }
            for leg in row.legs_new
        ]
        combos_out.append(
            {
                "underlying": row.underlying,
                "legs_close": legs_close,
                "legs_open": legs_open,
                "limit": round(float(row.debit_credit), 2),
            }
        )

    ticket = {"timestamp": dt.datetime.utcnow().isoformat(), "combos": combos_out}
    ticket_path = io.save(ticket, f"roll_ticket_{ts}", "json", outdir)

    csv_df = pd.DataFrame(
        {
            "underlying": df.underlying,
            "old_expiry": df.old_exp,
            "new_expiry": df.new_exp,
            "qty": df.qty,
            "debit_credit": df.debit_credit,
            "Δ_before": df.delta_before,
            "Δ_after": df.delta_after,
            "Θ_before": df.theta_before,
            "Θ_after": df.theta_after,
        }
    )
    preview_path = io.save(csv_df, f"roll_preview_{ts}", "csv", outdir)
    return {"ticket": ticket_path, "preview": preview_path}


def run(
    days: int | None = None,
    weekly: bool | None = None,
    fmt: str = "csv",
    return_df: bool = False,
    include_cal: bool = False,
    tenor: str = "all",
    pretty: bool = True,
    output_dir: str | pathlib.Path | None = None,
):
    """Interactive roll manager.

    Parameters
    ----------
    days : int | None
        Filter combos expiring within this many days.  When ``None`` the value
        is pulled from ``settings`` with a default of ``7``.
    weekly : bool | None
        ``True`` for weekly rolls, ``False`` for monthly.  ``None`` defers to the
        configuration.
    fmt : str
        Placeholder for future output formats.  Currently only ``csv`` is
        produced but the argument keeps parity with other scripts.
    return_df : bool
        When ``True`` the DataFrame of candidate rolls is returned.
    """

    interactive = not return_df

    cfg = getattr(settings, "roll", None)
    slippage = getattr(cfg, "slippage", 0.05) if cfg else 0.05
    if days is None:
        days = getattr(cfg, "default_days", 7) if cfg else 7
    if weekly is None:
        weekly = getattr(cfg, "use_weekly", False) if cfg else False

    global portfolio_greeks
    if portfolio_greeks is None:
        from portfolio_exporter.scripts import portfolio_greeks as _pg

        portfolio_greeks = _pg

    pos_df = run_with_spinner("Fetching positions…", portfolio_greeks._load_positions)
    if pos_df.empty:
        if return_df:
            return pd.DataFrame()
        return None

    combos_df = detect_combos(pos_df)
    if not include_cal and "type" in combos_df.columns:
        combos_df = combos_df[combos_df["type"] != "calendar"]
    if combos_df.empty:
        if return_df:
            return pd.DataFrame()
        return None

    today = dt.date.today()
    combos_df["expiry"] = pd.to_datetime(combos_df["expiry"]).dt.date
    mask = combos_df["expiry"] <= today + dt.timedelta(days=days)
    soon = combos_df[mask]
    if tenor != "all":
        def _is_weekly(d: dt.date) -> bool:
            return d != _third_friday(d.year, d.month)

        if tenor == "weekly":
            soon = soon[soon["expiry"].apply(_is_weekly)]
        else:
            soon = soon[~soon["expiry"].apply(_is_weekly)]
    if soon.empty:
        if return_df:
            return pd.DataFrame()
        return None

    console = None
    if interactive and pretty:
        from rich.console import Console
        from rich.table import Table

        console = Console(force_terminal=True)
    rows: List[dict] = []
    for cid, cmb in soon.iterrows():
        new_exp = _next_expiry(today, weekly)
        legs = cmb.legs
        strikes = list(pos_df.loc[legs, "strike"])
        rights = list(pos_df.loc[legs, "right"])
        qtys = list(pos_df.loc[legs, "qty"])
        mult = pos_df.loc[legs, "multiplier"].iloc[0] if "multiplier" in pos_df else 100
        chain = run_with_spinner(
            f"Pricing {cmb.underlying}", fetch_chain, cmb.underlying, new_exp, strikes
        )
        new_legs = []
        new_delta = 0.0
        new_theta = 0.0
        net_mid = 0.0
        for strike, right, qty in zip(strikes, rights, qtys):
            # --- ensure columns exist even if fetch_chain() set them as index ---
            if "strike" not in chain.columns:
                chain = chain.reset_index(drop=False, names=["strike"])  # pandas ≥2
            if "right" not in chain.columns:
                chain["right"] = (
                    chain.index.get_level_values("right")
                    if chain.index.nlevels > 1
                    else pd.NA
                )

            # IB/YF chains often list strikes in 5‑pt increments; roll to the
            # *nearest* available strike within $0.25 of the original.
            sel = chain[
                (chain["right"] == right) & (abs(chain["strike"] - strike) < 0.25)
            ]
            if sel.empty:
                if console:
                    console.print(
                        f"[yellow]⚠  No quote for {cmb.underlying} {strike}{right} {new_exp}. Skipping."
                    )
                else:
                    print(
                        f"⚠  No quote for {cmb.underlying} {strike}{right} {new_exp}. Skipping."
                    )
                continue
            ch = sel.iloc[0]
            new_legs.append(
                {
                    "strike": strike,
                    "right": right,
                    "qty": qty,
                }
            )
            new_delta += float(ch.get("delta", 0.0)) * qty
            new_theta += float(ch.get("theta", 0.0)) * qty
            net_mid += float(ch.get("mid", 0.0)) * qty

        old_delta = float((pos_df.loc[legs, "delta"] * pos_df.loc[legs, "qty"]).sum())
        old_theta = float((pos_df.loc[legs, "theta"] * pos_df.loc[legs, "qty"]).sum())
        debit_credit = net_mid + slippage * sum(qtys)
        cash_impact = debit_credit * mult

        rows.append(
            {
                "combo_id": cid,
                "underlying": cmb.underlying,
                "old_exp": cmb.expiry.isoformat(),
                "new_exp": new_exp,
                "legs_old": legs,
                "legs_new": new_legs,
                "debit_credit": debit_credit,
                "delta_change": new_delta - old_delta,
                "theta_change": new_theta - old_theta,
                "cash_impact": cash_impact,
                "qty": cmb.qty,
                "delta_before": old_delta,
                "delta_after": new_delta,
                "theta_before": old_theta,
                "theta_after": new_theta,
            }
        )

    if not rows:
        msg = "No eligible combos found or priced; nothing to roll."
        if console:
            console.print(f"[yellow]{msg}")
        else:
            print(msg)
        return pd.DataFrame() if return_df else None

    df = pd.DataFrame(rows).set_index("combo_id")
    if not interactive:
        return df if return_df else None

    selected: set = set()

    def _render() -> str | Table:
        if console:
            tbl = Table(show_edge=False)
            tbl.add_column("*")
            tbl.add_column("Under")
            tbl.add_column("Old")
            tbl.add_column("New")
            for idx, row in df.iterrows():
                mark = "*" if idx in selected else ""
                tbl.add_row(mark, row.underlying, str(row.old_exp), str(row.new_exp))
            return tbl
        lines = []
        for idx, row in df.iterrows():
            mark = "*" if idx in selected else ""
            lines.append(f"{mark} {row.underlying} {row.old_exp} {row.new_exp}")
        return "\n".join(lines)

    if console:
        console.print(_render())
    else:
        print(_render())
    while True:
        ch = input()
        if ch == " ":
            idx = df.index[0]
            if idx in selected:
                selected.remove(idx)
            else:
                selected.add(idx)
        elif ch.lower() == "r":
            _write_files(df.loc[list(selected)], pos_df, output_dir)
        elif ch.lower() == "q":
            break
        if console:
            console.print(_render())
        else:
            print(_render())

    return df if return_df else None


def cli(args: argparse.Namespace | None = None) -> dict | None:
    """CLI entry point for ``python -m portfolio_exporter.scripts.roll_manager``."""

    parser = argparse.ArgumentParser(description="Roll manager")
    cfg = getattr(settings, "roll", None)
    default_days = getattr(cfg, "default_days", 7) if cfg else 7
    parser.add_argument("--include-cal", action="store_true", help="Include calendars")
    parser.add_argument("--days", type=int, default=default_days, help="Expiry window")
    parser.add_argument(
        "--tenor", choices=["weekly", "monthly", "all"], default="all", help="Filter candidates"
    )
    parser.add_argument("--no-pretty", action="store_true", help="Disable rich tables")
    parser.add_argument("--json", action="store_true", help="Print JSON summary")
    parser.add_argument("--output-dir", help="Override output directory")
    if args is None:
        args = parser.parse_args()
    pretty = not args.no_pretty
    if args.json:
        df = run(
            days=args.days,
            include_cal=args.include_cal,
            tenor=args.tenor,
            pretty=False,
            output_dir=args.output_dir,
            return_df=True,
        )
        summary = {
            "n_candidates": int(len(df)),
            "n_selected": 0,
            "underlyings": sorted(df["underlying"].unique()) if not df.empty else [],
            "by_structure": df["structure"].value_counts().to_dict() if not df.empty else {},
            "outputs": [],
        }
        print(json.dumps(summary))
        return summary
    run(
        days=args.days,
        include_cal=args.include_cal,
        tenor=args.tenor,
        pretty=pretty,
        output_dir=args.output_dir,
    )
    return None


if __name__ == "__main__":  # pragma: no cover - CLI entry
    cli()


__all__ = ["run", "cli"]
