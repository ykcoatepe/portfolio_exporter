import os
import csv
import argparse
import pandas as pd
import yfinance as yf

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

# optional progress bar
try:
    from tqdm import tqdm

    PROGRESS = True
except ImportError:
    PROGRESS = False
from datetime import datetime

# ---------- IBKR optional integration ----------
try:
    from ib_insync import IB, Stock

    IB_AVAILABLE = True
except ImportError:
    IB_AVAILABLE = False

IB_HOST, IB_PORT, IB_CID = "127.0.0.1", 7497, 3  # separate clientId for historic pull

EXTRA_TICKERS = ["SPY", "QQQ", "IWM", "^VIX", "DX-Y.NYB"]  # core indices
PROXY_MAP = {"VIX": "^VIX", "VVIX": "^VVIX", "DXY": "DX-Y.NYB"}


def _tickers_from_ib() -> list[str]:
    """Return unique stock tickers from current IBKR account positions."""
    if not IB_AVAILABLE:
        return []
    ib = IB()
    try:
        ib.connect(IB_HOST, IB_PORT, clientId=IB_CID, timeout=3)
    except Exception:
        return []
    positions = ib.positions()
    ib.disconnect()
    if not positions:
        return []
    # extract underlying symbol for stocks only
    tickers = {
        p.contract.symbol.upper() for p in positions if p.contract.secType == "STK"
    }
    return sorted(tickers)


PORTFOLIO_FILES = ["tickers_live.txt", "tickers.txt"]  # first existing file wins

# Timestamped output (UTC). Includes time so repeated runs don't overwrite.
DATE_TAG = datetime.utcnow().strftime("%Y%m%d")
TIME_TAG = datetime.utcnow().strftime("%H%M")
# Save to iCloud Drive ▸ Downloads
OUTPUT_DIR = (
    "/Users/yordamkocatepe/Library/Mobile Documents/com~apple~CloudDocs/Downloads"
)
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_CSV = os.path.join(OUTPUT_DIR, f"historic_prices_{DATE_TAG}_{TIME_TAG}.csv")


def load_tickers() -> list[str]:
    """Return unique tickers prioritising IBKR holdings; otherwise text file."""
    # 1) try IBKR
    ib_tickers = _tickers_from_ib()
    if ib_tickers:
        mapped_ib = [PROXY_MAP.get(t, t) for t in ib_tickers]
        return sorted(set(mapped_ib + EXTRA_TICKERS))

    # 2) fallback to file
    path = next((p for p in PORTFOLIO_FILES if os.path.exists(p)), None)
    user_tickers = []
    if path:
        with open(path) as f:
            user_tickers = [line.strip().upper() for line in f if line.strip()]
    mapped = [PROXY_MAP.get(t, t) for t in user_tickers]
    return sorted(set(mapped + EXTRA_TICKERS))


def fetch_and_prepare_data(tickers):
    """
    Batch-fetch OHLCV data for tickers over last 60 days with daily interval.
    Raises ValueError if ticker list is empty.
    Returns DataFrame with columns:
    ["date","ticker","open","high","low","close","adj_close","volume"]
    """
    if not tickers:
        raise ValueError("No data fetched for any ticker.")
    data = yf.download(
        tickers=tickers,
        period="60d",
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
    )
    columns = ["date", "ticker", "open", "high", "low", "close", "adj_close", "volume"]
    if data.empty:
        return pd.DataFrame(columns=columns)
    dfs = []
    if isinstance(data.columns, pd.MultiIndex):
        iterable = tqdm(tickers, desc="split") if PROGRESS else tickers
        for ticker in iterable:
            if ticker in data:
                df_t = data[ticker].reset_index()
                df_t["Ticker"] = ticker
                dfs.append(df_t)
    else:
        df_t = data.reset_index()
        df_t["Ticker"] = tickers[0]
        dfs.append(df_t)
    result = pd.concat(dfs, ignore_index=True)
    # Rename columns and enforce types
    result = result.rename(
        columns={
            "Date": "date",
            "Ticker": "ticker",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Adj Close": "adj_close",
            "Volume": "volume",
        }
    )
    result["date"] = result["date"].dt.strftime("%Y-%m-%d")
    result["volume"] = result["volume"].fillna(0).astype(int)
    return result[columns]


def save_to_csv(df: pd.DataFrame):
    df.to_csv(
        OUTPUT_CSV,
        index=False,
        quoting=csv.QUOTE_MINIMAL,
        float_format="%.3f",
    )
    print(f"✅  Saved {len(df):,} rows → {OUTPUT_CSV}")


def save_to_excel(df: pd.DataFrame, path: str) -> None:
    with pd.ExcelWriter(
        path, engine="xlsxwriter", datetime_format="yyyy-mm-dd"
    ) as writer:
        df.to_excel(
            writer,
            sheet_name="Prices",
            index=False,
            float_format="%.3f",
        )


def save_to_pdf(df: pd.DataFrame, path: str) -> None:
    rows_data = [df.columns.tolist()] + df.values.tolist()
    doc = SimpleDocTemplate(
        path,
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
                ("FONTSIZE", (0, 0), (-1, -1), 6),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.black),
            ]
        )
    )
    doc.build([table])


def main() -> None:
    p = argparse.ArgumentParser(description="Download recent historical prices")
    out_grp = p.add_mutually_exclusive_group()
    out_grp.add_argument(
        "--excel",
        action="store_true",
        help="Save output as Excel instead of CSV.",
    )
    out_grp.add_argument(
        "--pdf",
        action="store_true",
        help="Save output as PDF instead of CSV.",
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

    tickers = load_tickers()
    df = fetch_and_prepare_data(tickers)
    if args.excel:
        path = OUTPUT_CSV.replace(".csv", ".xlsx")
        save_to_excel(df, path)
    elif args.pdf:
        path = OUTPUT_CSV.replace(".csv", ".pdf")
        save_to_pdf(df, path)
    else:
        save_to_csv(df)


if __name__ == "__main__":
    main()
