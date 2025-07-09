#!/usr/bin/env python3
"""
net_liq_history_export.py  –  Export end-of-day Net-Liq / equity curve

• First tries to read Trader Workstation’s auto-saved  dailyNetLiq.csv
  (TWS ▸ Account Window ▸ Reports ▸ “Export Directory”).
• If not present – or if you pass  --cp-download  – it pulls the same data
  from IBKR Client-Portal > PortfolioAnalyst (“Performance – Time Weighted”).
• Writes a cleaned CSV into the standard iCloud Downloads folder:
      net_liq_history_<YYYYMMDD-YYYYMMDD_HHMM>.csv
• With  --plot  it also drops a PNG equity-curve chart beside the CSV.

Usage
=====
$ python net_liq_history_export.py                     # auto date-range (all)
$ python net_liq_history_export.py --start 2024-01-01  # YTD
$ python net_liq_history_export.py --plot              # + chart
$ python net_liq_history_export.py --cp-download       # force CP REST fetch
"""

from __future__ import annotations
import argparse
import csv
import json
import os
import sys
from datetime import datetime, date
from pathlib import Path
from typing import Optional
import io

import pandas as pd  #  pandas ≥1.2
import requests  #  pip install requests

try:  # optional dependencies
    import xlsxwriter  # type: ignore
except Exception:  # pragma: no cover - optional
    xlsxwriter = None  # type: ignore

try:
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
except Exception:  # pragma: no cover - optional
    SimpleDocTemplate = Table = TableStyle = colors = letter = landscape = None

# ───────────────────────── CONFIG ──────────────────────────
OUTPUT_DIR = Path(
    "/Users/yordamkocatepe/Library/Mobile Documents/" "com~apple~CloudDocs/Downloads"
)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TIME_TAG = datetime.utcnow().strftime("%H%M")

# ---  1️⃣  where TWS writes dailyNetLiq.csv -----------------
# If you changed the “Export Directory” in TWS, edit here OR
# set the env-var  TWS_EXPORT_DIR
TWS_EXPORT_DIR = Path(os.getenv("TWS_EXPORT_DIR", "~/Jts/Export")).expanduser()
TWS_NET_LIQ_CSV = TWS_EXPORT_DIR / "dailyNetLiq.csv"

# ---  2️⃣  minimal Client-Portal credentials  ---------------
# Either export an env-var  CP_REFRESH_TOKEN
# or edit directly (never commit to git!)
CP_BASE = "https://localhost:5000/v1/api"  # default CP gateway
CP_TOKEN = os.getenv("CP_REFRESH_TOKEN", "")  # <your long-lived refresh token>
VERIFY_SSL = False  # CP’s self-signed cert


# ────────────────────── helper functions ───────────────────
def _parse_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure index is datetime.date, not string."""
    df.index = pd.to_datetime(df.index).date
    return df.sort_index()


def _read_tws_file() -> Optional[pd.DataFrame]:
    if not TWS_NET_LIQ_CSV.exists():
        return None
    df = pd.read_csv(TWS_NET_LIQ_CSV)
    if {"Date", "NetLiquidationByCurrency"}.issubset(df.columns):
        df = (
            df[["Date", "NetLiquidationByCurrency"]]
            .rename(columns={"NetLiquidationByCurrency": "net_liq"})
            .set_index("Date")
        )
        return _parse_dates(df)
    # unexpected format
    return None


def _pa_rest_download() -> pd.DataFrame:
    """
    Minimal PortfolioAnalyst /rest API call.
    Docs: https://interactivebrokers.github.io/cpwebapi/pa.html
    """
    if not CP_TOKEN:
        sys.exit("❌  Set CP_REFRESH_TOKEN env-var or edit CP_TOKEN in script.")

    session = requests.Session()
    session.verify = VERIFY_SSL

    # 1) refresh -> gateway’s time-limited bearer token
    r = session.post(f"{CP_BASE}/iserver/reauthorize", json={"refreshtoken": CP_TOKEN})
    r.raise_for_status()

    # 2) request the PA CSV
    params = {"acctIds": "", "fromDate": "", "toDate": "", "format": "CSV"}
    r = session.get(f"{CP_BASE}/pa/performance/timeweighted", params=params)
    r.raise_for_status()

    # CSV arrives as text
    df_all = pd.read_csv(io.StringIO(r.text))
    if {"Date", "NetLiquidation"}.issubset(df_all.columns):
        df = (
            df_all[["Date", "NetLiquidation"]]
            .rename(columns={"NetLiquidation": "net_liq"})
            .set_index("Date")
        )
        return _parse_dates(df)
    sys.exit("❌  Unexpected column layout from PortfolioAnalyst CSV.")


def _filter_range(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    if start:
        df = df[df.index >= datetime.fromisoformat(start).date()]
    if end:
        df = df[df.index <= datetime.fromisoformat(end).date()]
    return df


def _save_csv(df: pd.DataFrame, start_label: str, end_label: str) -> Path:
    out_name = f"net_liq_history_{start_label}-{end_label}_{TIME_TAG}.csv"
    out_path = OUTPUT_DIR / out_name
    df.to_csv(
        out_path, index_label="date", quoting=csv.QUOTE_MINIMAL, float_format="%.3f"
    )
    return out_path


def _save_excel(df: pd.DataFrame, start_label: str, end_label: str) -> Path:
    out_name = f"net_liq_history_{start_label}-{end_label}_{TIME_TAG}.xlsx"
    out_path = OUTPUT_DIR / out_name
    with pd.ExcelWriter(
        out_path, engine="xlsxwriter", datetime_format="yyyy-mm-dd"
    ) as writer:
        df.to_excel(
            writer, sheet_name="NetLiq", index_label="date", float_format="%.3f"
        )
    return out_path


def _save_pdf(df: pd.DataFrame, start_label: str, end_label: str) -> Path:
    # reportlab's Table object renders text directly, making the PDF text-based and searchable.
    out_name = f"net_liq_history_{start_label}-{end_label}_{TIME_TAG}.pdf"
    out_path = OUTPUT_DIR / out_name
    df_reset = df.reset_index()
    rows_data = [df_reset.columns.tolist()] + df_reset.values.tolist()
    doc = SimpleDocTemplate(
        out_path,
        pagesize=landscape(letter),
        rightMargin=18,
        leftMargin=18,
        topMargin=18,
        bottomMargin=18,
    )
    table = Table(rows_data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    10,
                ),  # Increased font size for better readability
                ("GRID", (0, 0), (-1, -1), 0.25, colors.black),
            ]
        )
    )
    doc.build([table])
    return out_path


def _save_txt(df: pd.DataFrame, start_label: str, end_label: str) -> Path:
    out_name = f"net_liq_history_{start_label}-{end_label}_{TIME_TAG}.txt"
    out_path = OUTPUT_DIR / out_name
    with open(out_path, "w") as fh:
        fh.write(df.to_string(index=True, float_format=lambda x: f"{x:.3f}"))
    return out_path


def _plot(df: pd.DataFrame, out_csv: Path):
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("⚠️  matplotlib not installed – skipping chart.")
        return
    fig, ax = plt.subplots()
    ax.plot(df.index, df["net_liq"])
    ax.set_title("Equity Curve (Net Liquidation)")
    ax.set_xlabel("Date")
    ax.set_ylabel("Net-Liq, USD")
    fig.autofmt_xdate()
    png_path = out_csv.with_suffix(".png")
    fig.savefig(png_path, dpi=110, bbox_inches="tight")
    print(f"📈  Saved chart → {png_path}")


# ─────────────────────────── MAIN ──────────────────────────
def main():
    p = argparse.ArgumentParser(description="Export Net-Liq / equity-curve history")
    p.add_argument("--start", help="YYYY-MM-DD (inclusive)")
    p.add_argument("--end", help="YYYY-MM-DD (inclusive)")
    p.add_argument("--plot", action="store_true", help="also create PNG chart")
    p.add_argument(
        "--cp-download",
        action="store_true",
        help="fetch via Client-Portal even if dailyNetLiq.csv exists",
    )
    out_grp = p.add_mutually_exclusive_group()
    out_grp.add_argument(
        "--excel",
        action="store_true",
        help="Save the output as an Excel workbook instead of CSV.",
    )
    out_grp.add_argument(
        "--pdf",
        action="store_true",
        help="Save the output as a PDF report instead of CSV.",
    )
    out_grp.add_argument(
        "--txt",
        action="store_true",
        help="Save the output as a plain text report instead of CSV.",
    )
    args = p.parse_args()

    if not args.excel and not args.pdf and not args.txt:
        try:
            choice = (
                input("Select output format [csv / excel / pdf / txt] (default csv): ")
                .strip()
                .lower()
            )
        except EOFError:
            choice = ""
        if choice == "excel" or choice == "xlsx":
            args.excel = True
        elif choice == "pdf":
            args.pdf = True
        elif choice == "txt":
            args.txt = True

    # 1) pick data source
    df: Optional[pd.DataFrame] = None
    if not args.cp_download:
        df = _read_tws_file()
        if df is not None:
            print(f"✅  Loaded {len(df):,} rows from dailyNetLiq.csv")
    if df is None:
        print("ℹ️  Pulling data from Client-Portal PortfolioAnalyst …")
        df = _pa_rest_download()

    # 2) optional date-range slice
    df = _filter_range(df, args.start, args.end)
    if df.empty:
        sys.exit("❌  No data in the selected date range.")

    start_lbl = df.index.min().strftime("%Y%m%d")
    end_lbl = df.index.max().strftime("%Y%m%d")

    if args.excel:
        out_path = _save_excel(df, start_lbl, end_lbl)
        print(f"💾  Saved Excel workbook → {out_path}")
    elif args.pdf:
        out_path = _save_pdf(df, start_lbl, end_lbl)
        print(f"💾  Saved PDF report   → {out_path}")
    elif args.txt:
        out_path = _save_txt(df, start_lbl, end_lbl)
        print(f"💾  Saved text report  → {out_path}")
    else:
        out_path = _save_csv(df, start_lbl, end_lbl)
        print(f"💾  Saved {len(df):,} rows → {out_path}")

    if args.plot:
        _plot(df, out_path if isinstance(out_path, Path) else Path(out_path))


if __name__ == "__main__":
    main()
