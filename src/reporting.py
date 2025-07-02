from __future__ import annotations

import csv
from typing import Iterable

import pandas as pd

try:
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
except Exception:  # pragma: no cover - optional
    SimpleDocTemplate = Table = TableStyle = colors = letter = landscape = None

try:
    from fpdf import FPDF
except Exception:  # pragma: no cover - optional
    FPDF = None  # type: ignore


def last_row(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values("date").groupby("ticker").tail(1).set_index("ticker")


def generate_report(df: pd.DataFrame, output_path: str, fmt: str = "csv") -> None:
    """Write the latest metrics for each ticker to ``output_path``."""
    latest = (
        df.sort_values("date")
        .groupby("ticker", as_index=False)
        .tail(1)
        .set_index("ticker", drop=True)
    )
    cols = [
        "close",
        "pct_change",
        "sma20",
        "ema20",
        "atr14",
        "rsi14",
        "macd",
        "macd_signal",
        "bb_upper",
        "bb_lower",
        "vwap",
        "real_vol_30",
    ]
    cols = [c for c in cols if c in latest.columns]
    latest = latest[cols].round(3)

    if fmt == "excel":
        with pd.ExcelWriter(
            output_path, engine="xlsxwriter", datetime_format="yyyy-mm-dd"
        ) as writer:
            latest.reset_index().to_excel(
                writer, sheet_name="Pulse", index=False, float_format="%.3f"
            )
    elif fmt == "pdf":
        if SimpleDocTemplate is None:
            raise RuntimeError("reportlab is required for PDF output")
        rows = [
            latest.reset_index().columns.tolist()
        ] + latest.reset_index().values.tolist()
        doc = SimpleDocTemplate(
            output_path,
            pagesize=landscape(letter),
            rightMargin=18,
            leftMargin=18,
            topMargin=18,
            bottomMargin=18,
        )
        table = Table(rows, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.black),
                ]
            )
        )
        doc.build([table])
    else:
        latest.to_csv(output_path, quoting=csv.QUOTE_MINIMAL, float_format="%.3f")


def save_csv(df: pd.DataFrame, path: str) -> None:
    """Save ``df`` to ``path`` as CSV without index."""

    df.to_csv(path, index=False)


def save_excel(df: pd.DataFrame, path: str) -> None:
    """Save ``df`` to ``path`` as an Excel workbook."""

    with pd.ExcelWriter(
        path, engine="xlsxwriter", datetime_format="yyyy-mm-dd"
    ) as writer:
        df.to_excel(writer, index=False)


def save_pdf(df: pd.DataFrame, path: str) -> None:
    """Save ``df`` to ``path`` as a simple PDF table."""

    if FPDF is None:
        raise RuntimeError("fpdf is required for PDF output")

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=8)
    page_width = pdf.w - 2 * pdf.l_margin
    col_width = page_width / len(df.columns)

    for col in df.columns:
        pdf.cell(col_width, 8, str(col), border=1)
    pdf.ln(8)

    for _, row in df.iterrows():
        for val in row:
            pdf.cell(col_width, 8, str(val), border=1)
        pdf.ln(8)

    pdf.output(path)


def save_table(df: pd.DataFrame, path: str, fmt: str = "csv") -> None:
    """Save ``df`` using the given format."""

    if fmt == "excel":
        save_excel(df, path)
    elif fmt == "pdf":
        save_pdf(df, path)
    else:
        save_csv(df, path)
