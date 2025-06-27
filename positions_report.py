#!/usr/bin/env python3
"""Export current IBKR positions to CSV or PDF."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

import pandas as pd

from daily_pulse import load_ib_positions_ib

try:
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
except Exception:  # pragma: no cover - optional dependency
    SimpleDocTemplate = None  # type: ignore
    Table = None  # type: ignore
    TableStyle = None  # type: ignore
    colors = None  # type: ignore
    letter = None  # type: ignore
    landscape = None  # type: ignore

TIME_TAG = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%H%M")
DATE_TAG = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%Y%m%d")
OUTPUT_DIR = Path(
    "/Users/yordamkocatepe/Library/Mobile Documents/" "com~apple~CloudDocs/Downloads"
)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def save_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL, float_format="%.3f")


def save_pdf(df: pd.DataFrame, path: Path) -> None:
    if SimpleDocTemplate is None:
        raise RuntimeError("reportlab is required for PDF output")
    data = [df.columns.tolist()] + df.values.tolist()
    doc = SimpleDocTemplate(
        str(path),
        pagesize=landscape(letter),
        rightMargin=18,
        leftMargin=18,
        topMargin=18,
        bottomMargin=18,
    )
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.darkblue),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.black),
            ]
        )
    )
    doc.build([table])


def main() -> None:
    p = argparse.ArgumentParser(description="Export current IBKR positions")
    p.add_argument(
        "--pdf", action="store_true", help="Save output as PDF instead of CSV."
    )
    args = p.parse_args()

    df = load_ib_positions_ib()
    base = OUTPUT_DIR / f"positions_{DATE_TAG}_{TIME_TAG}"
    if args.pdf:
        out = base.with_suffix(".pdf")
        save_pdf(df, out)
    else:
        out = base.with_suffix(".csv")
        save_csv(df, out)
    print(f"\u2705 Saved positions → {out}")


if __name__ == "__main__":
    main()
