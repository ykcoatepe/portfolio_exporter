#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from rich.console import Console

from portfolio_exporter.core import cli as cli_helpers
from portfolio_exporter.core import json as json_helpers
from portfolio_exporter.core import io as core_io
from portfolio_exporter.core.runlog import RunLog
from portfolio_exporter.core.config import settings

try:  # optional dependency for PDF output
    from reportlab.platypus import (
        SimpleDocTemplate,
        Table as RLTable,
        Paragraph,
        PageBreak,
    )
    from reportlab.lib.styles import getSampleStyleSheet
except Exception:  # pragma: no cover - optional
    (
        SimpleDocTemplate,
        RLTable,
        Paragraph,
        PageBreak,
        getSampleStyleSheet,
    ) = (None,) * 5


# ---------------------------------------------------------------------------
# data loaders & helpers

def _load_csv(name: str) -> pd.DataFrame:
    path = core_io.latest_file(name)
    if not path or not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _prep_positions(df: pd.DataFrame, since: str | None, until: str | None) -> pd.DataFrame:
    if df.empty:
        return df
    if "expiry" in df.columns:
        df["expiry"] = pd.to_datetime(df["expiry"], errors="coerce").dt.date
        if since:
            df = df[df["expiry"] >= datetime.fromisoformat(since).date()]
        if until:
            df = df[df["expiry"] <= datetime.fromisoformat(until).date()]
        df["expiry"] = df["expiry"].astype(str)
    cols = ["underlying", "right", "strike", "expiry", "qty"]
    greek_cols = [c for c in ["delta", "gamma", "vega", "theta"] if c in df.columns]
    exposure_cols = [
        c
        for c in ["delta_exposure", "gamma_exposure", "vega_exposure", "theta_exposure"]
        if c in df.columns
    ]
    keep = [c for c in cols + greek_cols + exposure_cols if c in df.columns]
    return df[keep]


def _prep_combos(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    if "expiry" in df.columns:
        df["expiry"] = pd.to_datetime(df["expiry"], errors="coerce").dt.date.astype(str)
    cols = [
        "underlying",
        "expiry",
        "structure_label",
        "structure",
        "type",
        "width",
        "strikes",
        "call_strikes",
        "put_strikes",
        "call_count",
        "put_count",
        "legs_n",
    ]
    df = df[[c for c in cols if c in df.columns]]
    if "structure_label" in df.columns:
        df = df.rename(columns={"structure_label": "structure"})
    return df.sort_values(["underlying", "expiry"], ascending=[True, False]).head(50)


def _filter_symbol(df: pd.DataFrame, symbol: str | None) -> pd.DataFrame:
    if not symbol or df.empty or "underlying" not in df.columns:
        return df
    return df[df["underlying"].str.upper() == symbol.upper()]


def _expiry_radar(
    df_combos: pd.DataFrame,
    df_positions: pd.DataFrame,
    window_days: int,
    console: Console | None = None,
) -> dict[str, Any]:
    basis = "combos" if not df_combos.empty else "positions"
    df = df_combos if basis == "combos" else df_positions
    result: dict[str, Any] = {
        "window_days": window_days,
        "basis": basis,
        "rows": [],
    }
    if df.empty or window_days <= 0:
        return result
    if "expiry" not in df.columns:
        if console:
            console.print("Expiry radar: missing 'expiry' column", style="yellow")
        return result
    exp = pd.to_datetime(df["expiry"], errors="coerce")
    now = pd.Timestamp(datetime.now().date())
    df = df.copy()
    df["expiry_dt"] = exp
    df = df.dropna(subset=["expiry_dt"])
    df["days"] = (df["expiry_dt"] - now).dt.days
    df = df[(df["days"] >= 0) & (df["days"] <= window_days)]
    if df.empty:
        return result
    delta_col = (
        "delta_exposure"
        if "delta_exposure" in df.columns
        else "delta" if "delta" in df.columns else None
    )
    theta_col = (
        "theta_exposure"
        if "theta_exposure" in df.columns
        else "theta" if "theta" in df.columns else None
    )
    rows: list[dict[str, Any]] = []
    for date, grp in df.groupby(df["expiry_dt"].dt.date):
        row: dict[str, Any] = {"date": date.isoformat(), "count": int(len(grp))}
        if delta_col:
            row["delta_total"] = float(grp[delta_col].sum())
        if theta_col:
            row["theta_total"] = float(grp[theta_col].sum())
        if basis == "combos" and "structure" in grp.columns:
            by_struct = grp.groupby("structure").size().to_dict()
            row["by_structure"] = {str(k): int(v) for k, v in by_struct.items()}
        rows.append(row)
    result["rows"] = sorted(rows, key=lambda r: r["date"])
    return result


# ---------------------------------------------------------------------------
# analytics


def _delta_buckets(df: pd.DataFrame) -> dict[str, int]:
    labels = [
        "(-1,-0.6]",
        "(-0.6,-0.3]",
        "(-0.3,0]",
        "(0,0.3]",
        "(0.3,0.6]",
        "(0.6,1]",
    ]
    counts = {label: 0 for label in labels}
    if df.empty or "delta" not in df.columns:
        return counts
    bins = [-1.0, -0.6, -0.3, 0.0, 0.3, 0.6, 1.0]
    binned = pd.cut(df["delta"], bins=bins, labels=labels, include_lowest=True)
    vc = binned.value_counts().reindex(labels, fill_value=0)
    return {label: int(vc[label]) for label in labels}


def _theta_decay_5d(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    theta_col = (
        "theta_exposure"
        if "theta_exposure" in df.columns
        else "theta" if "theta" in df.columns else None
    )
    if theta_col is None:
        return 0.0
    return float(df[theta_col].sum() * 5)


# ---------------------------------------------------------------------------
# output builders


def _build_html(
    outdir: Path,
    totals: pd.DataFrame,
    combos: pd.DataFrame,
    positions: pd.DataFrame,
    account: str | None,
    expiry_radar: dict[str, Any] | None,
    delta_buckets: dict[str, int] | None = None,
    theta_decay_5d: float | None = None,
    link_theme: bool = False,
) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    head: list[str] = []
    if link_theme:
        head.append('<link rel="stylesheet" href="theme.css">')
    parts = ["<html>", "<head>", *head, "</head>", "<body>"]
    parts.append("<h1>Daily Portfolio Report</h1>")
    meta: list[str] = [f"<p>Generated: {ts}</p>"]
    if account:
        meta.append(f"<p>Account: {account}</p>")
    meta.append(f"<p>Output dir: {outdir}</p>")
    parts.append('<section class="card">' + "".join(meta) + "</section>")
    if expiry_radar is not None:
        sec_parts = [
            f"<h2>Expiry Radar (next {expiry_radar['window_days']} days)</h2>",
        ]
        rows = expiry_radar.get("rows", [])
        if rows:
            tab_rows: list[dict[str, Any]] = []
            for r in rows:
                r = r.copy()
                if "by_structure" in r:
                    r["by_structure"] = "; ".join(
                        f"{k}: {v}" for k, v in r["by_structure"].items()
                    )
                tab_rows.append(r)
            sec_parts.append(pd.DataFrame(tab_rows).to_html(index=False))
        else:
            sec_parts.append("<p>No expiries within window.</p>")
        parts.append('<section class="card">' + "".join(sec_parts) + "</section>")
    if delta_buckets is not None:
        db_df = pd.DataFrame({
            "bucket": list(delta_buckets.keys()),
            "count": list(delta_buckets.values()),
        })
        parts.append(
            '<section class="card"><h2>Delta Buckets</h2>'
            + db_df.to_html(index=False)
            + "</section>"
        )
    if theta_decay_5d is not None:
        parts.append(
            '<section class="card"><h2>Theta Decay 5d</h2>'
            + f"<p>{theta_decay_5d}</p>"
            + "</section>"
        )
    if not totals.empty:
        parts.append(
            '<section class="card"><h2>Totals</h2>'
            + totals.to_html(index=False)
            + "</section>"
        )
    if not combos.empty:
        parts.append(
            '<section class="card"><h2>Combos</h2>'
            + combos.to_html(index=False)
            + "</section>"
        )
    if not positions.empty:
        parts.append(
            '<section class="card"><h2>Positions</h2>'
            + positions.to_html(index=False)
            + "</section>"
        )
    parts.append("</body></html>")
    return "\n".join(parts)


def _build_pdf_flowables(
    outdir: Path,
    totals: pd.DataFrame,
    combos: pd.DataFrame,
    positions: pd.DataFrame,
    account: str | None,
    expiry_radar: dict[str, Any] | None,
    delta_buckets: dict[str, int] | None = None,
    theta_decay_5d: float | None = None,
):
    if SimpleDocTemplate is None:
        return []
    styles = getSampleStyleSheet()
    flow = [Paragraph("Daily Portfolio Report", styles["Heading1"])]
    flow.append(Paragraph(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), styles["Normal"]))
    if account:
        flow.append(Paragraph(f"Account: {account}", styles["Normal"]))
    flow.append(Paragraph(f"Output dir: {outdir}", styles["Normal"]))
    if expiry_radar is not None:
        flow.append(
            Paragraph(
                f"Expiry Radar (next {expiry_radar['window_days']} days)",
                styles["Heading2"],
            )
        )
        rows = expiry_radar.get("rows", [])
        if rows:
            tab_rows = []
            for r in rows:
                r = r.copy()
                if "by_structure" in r:
                    r["by_structure"] = ", ".join(
                        f"{k}: {v}" for k, v in r["by_structure"].items()
                    )
                tab_rows.append(r)
            df_r = pd.DataFrame(tab_rows)
            flow.append(RLTable([df_r.columns.tolist()] + df_r.values.tolist()))
        else:
            flow.append(Paragraph("No expiries within window.", styles["Normal"]))
    if delta_buckets is not None:
        flow.append(Paragraph("Delta Buckets", styles["Heading2"]))
        df_b = pd.DataFrame({
            "bucket": list(delta_buckets.keys()),
            "count": list(delta_buckets.values()),
        })
        flow.append(RLTable([df_b.columns.tolist()] + df_b.values.tolist()))
    if theta_decay_5d is not None:
        flow.append(Paragraph("Theta Decay 5d", styles["Heading2"]))
        flow.append(Paragraph(str(theta_decay_5d), styles["Normal"]))
    if not totals.empty:
        flow.append(Paragraph("Totals", styles["Heading2"]))
        flow.append(RLTable([totals.columns.tolist()] + totals.values.tolist()))
    if not combos.empty:
        flow.append(PageBreak())
        flow.append(Paragraph("Combos", styles["Heading2"]))
        flow.append(RLTable([combos.columns.tolist()] + combos.values.tolist()))
    if not positions.empty:
        flow.append(PageBreak())
        flow.append(Paragraph("Positions", styles["Heading2"]))
        flow.append(RLTable([positions.columns.tolist()] + positions.values.tolist()))
    return flow


# ---------------------------------------------------------------------------
# main


def get_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render portfolio report from latest CSVs")
    parser.add_argument("--html", action="store_true")
    parser.add_argument("--pdf", action="store_true")
    cli_helpers.add_common_output_args(parser, include_excel=True)
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--combos-source", default="csv")
    parser.add_argument("--expiry-window", type=int, nargs="?", const=10, default=None)
    parser.add_argument("--symbol")
    parser.add_argument("--preflight", action="store_true")
    cli_helpers.add_common_debug_args(parser)
    return parser


def main(argv: list[str] | None = None) -> dict:
    parser = get_arg_parser()
    args = parser.parse_args(argv)

    formats = cli_helpers.decide_file_writes(
        args,
        json_only_default=True,
        defaults={"html": True, "pdf": True, "excel": False},
    )
    outdir = cli_helpers.resolve_output_dir(args.output_dir)
    quiet, pretty = cli_helpers.resolve_quiet(args.no_pretty)
    console = Console() if pretty else None

    if args.preflight:
        from portfolio_exporter.core import schemas as pa_schemas

        warnings: list[str] = []
        ok = True
        files = {
            "positions": core_io.latest_file("portfolio_greeks_positions"),
            "totals": core_io.latest_file("portfolio_greeks_totals"),
            "combos": core_io.latest_file("portfolio_greeks_combos"),
        }
        missing_any = False
        for name, path in files.items():
            if not path or not path.exists():
                warnings.append(f"missing {name} csv")
                missing_any = True
                continue
            try:
                df = pd.read_csv(path)
            except Exception as e:
                warnings.append(f"{path.name}: {e}")
                ok = False
                continue
            msgs = pa_schemas.check_headers(name, df)
            warnings.extend([f"{path.name}: {m}" for m in msgs])
            if msgs and not any("pandera" in m for m in msgs):
                ok = False
        # Provide an actionable hint when inputs are missing
        if missing_any:
            warnings.append("run: portfolio-greeks to generate latest CSVs")
        summary = json_helpers.report_summary({}, outputs={}, warnings=warnings, meta={"script": "daily_report"})
        summary["ok"] = ok
        if args.json:
            cli_helpers.print_json(summary, quiet)
        # When invoked via console entry (argv is None), return an int exit code
        # to avoid sys.exit(dict) printing a Python repr to stderr.
        return 0 if argv is None else summary

    with RunLog(script="daily_report", args=vars(args), output_dir=outdir) as rl:
        with rl.time("load_data"):
            positions = _prep_positions(
                _load_csv("portfolio_greeks_positions"), args.since, args.until
            )
            totals = _load_csv("portfolio_greeks_totals")
            combos_raw = _load_csv("portfolio_greeks_combos")

            # Optional symbol filter
            if args.symbol:
                positions = _filter_symbol(positions, args.symbol)
                totals = _filter_symbol(totals, args.symbol)
                combos_raw = _filter_symbol(combos_raw, args.symbol)

        meta: dict[str, Any] = {}
        if args.symbol:
            meta["filters"] = {"symbol": args.symbol.upper()}

        with rl.time("analytics"):
            combos = _prep_combos(combos_raw)

            account = (
                totals["account"].iloc[0]
                if "account" in totals.columns and not totals.empty
                else None
            )

            # Expiry radar (exposed at top-level via meta back-compat)
            expiry_radar = None
            if args.expiry_window and args.expiry_window > 0:
                expiry_radar = _expiry_radar(combos, positions, args.expiry_window, console)
                meta["expiry_radar"] = expiry_radar

            # Analytics (live under sections)
            delta_buckets = _delta_buckets(positions)
            theta_decay_5d = _theta_decay_5d(positions)

            # Pre-build HTML for HTML/PDF requests
            html_str = None
            # Locate stylesheet: prefer repo docs; fallback to packaged asset
            theme_css = (
                Path(__file__).resolve().parents[2] / "docs" / "assets" / "theme.css"
            )
            if not theme_css.exists():
                theme_css = Path(__file__).resolve().parents[1] / "assets" / "theme.css"
            link_theme = theme_css.exists()
            if formats.get("html") or formats.get("pdf"):
                html_str = _build_html(
                    outdir,
                    totals,
                    combos,
                    positions,
                    account,
                    expiry_radar,
                    delta_buckets,
                    theta_decay_5d,
                    link_theme=link_theme,
                )

        # File outputs plan and writes
        outputs: dict[str, str] = {k: "" for k in formats}
        written: list[Path] = []

        with rl.time("write_outputs"):
            if formats.get("html") and html_str is not None:
                path_html = core_io.save(html_str, "daily_report", "html", outdir)
                outputs["html"] = str(path_html)
                written.append(path_html)
                if console:
                    console.print(f"HTML report → {path_html}")
                if link_theme:
                    try:
                        shutil.copy(theme_css, outdir / "theme.css")
                    except Exception:
                        pass

            if formats.get("pdf"):
                flowables = _build_pdf_flowables(
                    outdir,
                    totals,
                    combos,
                    positions,
                    account,
                    expiry_radar,
                    delta_buckets,
                    theta_decay_5d,
                )
                path_pdf = core_io.save(flowables, "daily_report", "pdf", outdir)
                outputs["pdf"] = str(path_pdf)
                written.append(path_pdf)
                if console:
                    console.print(f"PDF report → {path_pdf}")

            # Optional Excel workbook output
            if formats.get("excel"):
                try:
                    import openpyxl  # noqa: F401  # ensure engine available
                except Exception:
                    # Gracefully skip when openpyxl is not installed
                    if console:
                        console.print("Skipping XLSX: openpyxl not installed", style="yellow")
                else:
                    xlsx_path = outdir / "daily_report.xlsx"
                    try:
                        with pd.ExcelWriter(xlsx_path, engine="openpyxl") as xw:
                            # Write available sections to dedicated sheets
                            if not totals.empty:
                                totals.to_excel(xw, index=False, sheet_name="Totals")
                            if not combos.empty:
                                combos.to_excel(xw, index=False, sheet_name="Combos")
                            if not positions.empty:
                                positions.to_excel(xw, index=False, sheet_name="Positions")
                            # Add small analytics sheets for quick reference
                            if expiry_radar and expiry_radar.get("rows"):
                                pd.DataFrame(expiry_radar["rows"]).to_excel(
                                    xw, index=False, sheet_name="ExpiryRadar"
                                )
                            if delta_buckets is not None:
                                pd.DataFrame(
                                    {
                                        "bucket": list(delta_buckets.keys()),
                                        "count": list(delta_buckets.values()),
                                    }
                                ).to_excel(xw, index=False, sheet_name="DeltaBuckets")
                    except Exception:
                        # If writing fails for any reason, don't crash
                        pass
                    else:
                        outputs["excel"] = str(xlsx_path)
                        written.append(xlsx_path)
                        if console:
                            console.print(f"XLSX report → {xlsx_path}")

            if args.debug_timings:
                meta["timings"] = rl.timings
                if written:
                    path_t = core_io.save(pd.DataFrame(rl.timings), "timings", "csv", outdir)
                    outputs["timings"] = str(path_t)
                    written.append(path_t)

        # Manifest
        rl.add_outputs(written)
        manifest_path = rl.finalize(write=bool(written))
        if manifest_path:
            written.append(manifest_path)

        # Sections: counts + analytics
        sections: dict[str, Any] = {
            "positions": len(positions),
            "combos": len(combos),
            "totals": len(totals),
            "delta_buckets": delta_buckets,
            "theta_decay_5d": theta_decay_5d,
        }

        # Summary: outputs mapping becomes list via helper
        summary = json_helpers.report_summary(
            sections,
            outputs=outputs,
            meta=meta or None,
        )
        if manifest_path:
            summary["outputs"].append(str(manifest_path))

        # Back-compat row counts + select meta surfacing
        summary["positions_rows"] = len(positions)
        summary["combos_rows"] = len(combos)
        summary["totals_rows"] = len(totals)
        summary.update(meta)

        if args.json:
            cli_helpers.print_json(summary, quiet)
        return 0 if argv is None else summary


if __name__ == "__main__":  # pragma: no cover
    main()
