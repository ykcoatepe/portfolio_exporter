#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
from rich.console import Console

from portfolio_exporter.core import io as core_io
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
# data loaders


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


# ---------------------------------------------------------------------------
# output builders


def _build_html(
    outdir: Path, totals: pd.DataFrame, combos: pd.DataFrame, positions: pd.DataFrame, account: str | None
) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parts = ["<h1>Daily Portfolio Report</h1>"]
    parts.append(f"<p>Generated: {ts}</p>")
    if account:
        parts.append(f"<p>Account: {account}</p>")
    parts.append(f"<p>Output dir: {outdir}</p>")
    if not totals.empty:
        parts.append("<h2>Totals</h2>")
        parts.append(totals.to_html(index=False))
    if not combos.empty:
        parts.append("<h2>Combos</h2>")
        parts.append(combos.to_html(index=False))
    if not positions.empty:
        parts.append("<h2>Positions</h2>")
        parts.append(positions.to_html(index=False))
    return "\n".join(parts)


def _build_pdf_flowables(
    outdir: Path, totals: pd.DataFrame, combos: pd.DataFrame, positions: pd.DataFrame, account: str | None
):
    if SimpleDocTemplate is None:
        return []
    styles = getSampleStyleSheet()
    flow = [Paragraph("Daily Portfolio Report", styles["Heading1"])]
    flow.append(Paragraph(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), styles["Normal"]))
    if account:
        flow.append(Paragraph(f"Account: {account}", styles["Normal"]))
    flow.append(Paragraph(f"Output dir: {outdir}", styles["Normal"]))
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


def main(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser(description="Render portfolio report from latest CSVs")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--html", action="store_true")
    parser.add_argument("--pdf", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-files", action="store_true", help="Do not write HTML/PDF outputs; emit JSON only if --json is set")
    parser.add_argument("--no-pretty", action="store_true")
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--combos-source", default="csv")
    args = parser.parse_args(argv)

    # Default to writing both HTML and PDF unless explicitly disabled.
    # When --no-files is provided, suppress file outputs (useful for sandboxed JSON-only runs).
    if args.no_files:
        args.html = args.pdf = False
    elif not args.html and not args.pdf:
        args.html = args.pdf = True

    console = Console() if not args.no_pretty else None

    positions = _prep_positions(_load_csv("portfolio_greeks_positions"), args.since, args.until)
    totals = _load_csv("portfolio_greeks_totals")
    combos = _prep_combos(_load_csv("portfolio_greeks_combos"))

    outdir = Path(args.output_dir or settings.output_dir).expanduser()
    account = totals["account"].iloc[0] if "account" in totals.columns and not totals.empty else None

    summary = {
        "positions_rows": len(positions),
        "combos_rows": len(combos),
        "totals_rows": len(totals),
        "outputs": {},
    }

    html_str = None
    if args.html or args.pdf:
        html_str = _build_html(outdir, totals, combos, positions, account)

    if args.html and html_str is not None:
        path_html = core_io.save(html_str, "daily_report", "html", outdir)
        summary["outputs"]["html"] = str(path_html)
        if console:
            console.print(f"HTML report → {path_html}")
    if args.pdf:
        flowables = _build_pdf_flowables(outdir, totals, combos, positions, account)
        path_pdf = core_io.save(flowables, "daily_report", "pdf", outdir)
        summary["outputs"]["pdf"] = str(path_pdf)
        if console:
            console.print(f"PDF report → {path_pdf}")

    if args.json:
        print(json.dumps(summary))
    return summary


if __name__ == "__main__":  # pragma: no cover
    main()
