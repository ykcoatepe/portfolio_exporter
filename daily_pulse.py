import os
import argparse
from datetime import datetime

import pandas as pd
import numpy as np

try:  # optional dependencies
    import xlsxwriter  # type: ignore
except Exception:  # pragma: no cover - optional
    xlsxwriter = None  # type: ignore

try:  # optional dependencies
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
except Exception:  # pragma: no cover - optional
    SimpleDocTemplate = Table = TableStyle = colors = letter = landscape = None

DATE_TAG = datetime.utcnow().strftime("%Y%m%d")
TIME_TAG = datetime.utcnow().strftime("%H%M")
OUTPUT_DIR = (
    "/Users/yordamkocatepe/Library/Mobile Documents/com~apple~CloudDocs/Downloads"
)
os.makedirs(OUTPUT_DIR, exist_ok=True)
DEFAULT_OUTPUT = os.path.join(OUTPUT_DIR, f"daily_pulse_{DATE_TAG}_{TIME_TAG}.csv")


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Return DataFrame with technical indicators."""
    df = df.sort_values("date").copy()
    grp = df.groupby("ticker")
    df["pct_change"] = grp["close"].pct_change(fill_method=None)
    df["sma20"] = grp["close"].transform(lambda s: s.rolling(20, min_periods=1).mean())
    df["ema20"] = grp["close"].transform(lambda s: s.ewm(span=20, min_periods=1).mean())
    high_low = df["high"] - df["low"]
    prev_close = grp["close"].shift(1)
    tr = pd.concat(
        [
            high_low,
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["tr"] = tr
    df["atr14"] = grp["tr"].transform(lambda s: s.rolling(14, min_periods=1).mean())
    df.drop(columns="tr", inplace=True)
    delta = grp["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14, min_periods=1).mean()
    avg_loss = loss.rolling(14, min_periods=1).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi14"] = 100 - (100 / (1 + rs))
    ema12 = grp["close"].transform(lambda s: s.ewm(span=12, min_periods=1).mean())
    ema26 = grp["close"].transform(lambda s: s.ewm(span=26, min_periods=1).mean())
    df["macd"] = ema12 - ema26
    df["macd_signal"] = grp["macd"].transform(
        lambda s: s.ewm(span=9, min_periods=1).mean()
    )
    rolling_mean = grp["close"].transform(lambda s: s.rolling(20, min_periods=1).mean())
    rolling_std = grp["close"].transform(lambda s: s.rolling(20, min_periods=1).std())
    df["bb_upper"] = rolling_mean + 2 * rolling_std
    df["bb_lower"] = rolling_mean - 2 * rolling_std
    df["vwap"] = (df["close"] * df["volume"]).groupby(df["ticker"]).cumsum() / df[
        "volume"
    ].groupby(df["ticker"]).cumsum()
    df["real_vol_30"] = grp["pct_change"].transform(
        lambda s: s.rolling(30, min_periods=1).std() * np.sqrt(252)
    )
    return df


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

    # keep only existing cols to prevent key errors
    cols = [c for c in cols if c in latest.columns]

    latest = latest[cols].round(4)

    if fmt == "excel":
        with pd.ExcelWriter(
            output_path, engine="xlsxwriter", datetime_format="yyyy-mm-dd"
        ) as writer:
            latest.reset_index().to_excel(writer, sheet_name="Pulse", index=False)
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
        latest.to_csv(output_path)


def main() -> None:
    p = argparse.ArgumentParser(
        description="Generate daily technical summary from OHLC data"
    )
    p.add_argument(
        "csv",
        nargs="?",
        default="historic_prices_sample.csv",
        help="Input OHLCV CSV file",
    )
    out_grp = p.add_mutually_exclusive_group()
    out_grp.add_argument(
        "--excel",
        action="store_true",
        help="Save the summary as an Excel workbook instead of CSV.",
    )
    out_grp.add_argument(
        "--pdf",
        action="store_true",
        help="Save the summary as a PDF report instead of CSV.",
    )
    p.add_argument(
        "-o",
        "--output",
        default=DEFAULT_OUTPUT,
        help="Path to save the summary file",
    )
    args = p.parse_args()

    if not args.excel and not args.pdf:
        try:
            choice = (
                input("Select output format [csv / excel / pdf] (default csv): ")
                .strip()
                .lower()
            )
        except EOFError:
            choice = ""
        if choice in {"excel", "xlsx"}:
            args.excel = True
        elif choice == "pdf":
            args.pdf = True

    fmt = "excel" if args.excel else "pdf" if args.pdf else "csv"
    output_path = args.output
    if fmt == "excel" and output_path.endswith(".csv"):
        output_path = output_path[:-4] + ".xlsx"
    elif fmt == "pdf" and output_path.endswith(".csv"):
        output_path = output_path[:-4] + ".pdf"

    df = pd.read_csv(args.csv, parse_dates=["date"])
    df = compute_indicators(df)
    generate_report(df, output_path, fmt)
    print(f"✅  Saved report → {output_path}")


if __name__ == "__main__":
    main()
