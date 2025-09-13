from __future__ import annotations

import csv
import glob
import os
from typing import Dict, Iterable, List, Optional

from .micro_momo_types import ChainRow, ScanRow


def load_scan_csv(path: str) -> List[ScanRow]:
    rows: List[ScanRow] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            rows.append(ScanRow.from_csv_row(raw))
    return rows


def load_chain_csv(path: str) -> List[ChainRow]:
    rows: List[ChainRow] = []
    # Infer expiry from filename like SYMBOL_YYYYMMDD.csv
    base = os.path.basename(path)
    expiry = ""
    parts = os.path.splitext(base)[0].split("_")
    if len(parts) >= 2 and parts[-1].isdigit():
        expiry = parts[-1]
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            symbol = str(raw.get("symbol", "")).upper()
            right = str(raw.get("right", "")).upper()[:1]
            try:
                row = ChainRow(
                    symbol=symbol,
                    expiry=str(raw.get("expiry", expiry)) or expiry,
                    right=right,
                    strike=float(raw.get("strike", 0.0)),
                    bid=float(raw.get("bid", 0.0)),
                    ask=float(raw.get("ask", 0.0)),
                    last=float(raw.get("last", 0.0)),
                    volume=int(float(raw.get("volume", 0))),
                    oi=int(float(raw.get("oi", 0))),
                )
                rows.append(row)
            except Exception:
                continue
    # Sort by strike then right for stability
    rows.sort(key=lambda r: (r.expiry, r.right, r.strike))
    return rows


def find_chain_file_for_symbol(chains_dir: Optional[str], symbol: str) -> Optional[str]:
    if not chains_dir:
        return None
    pattern = os.path.join(chains_dir, f"{symbol.upper()}_*.csv")
    matches = sorted(glob.glob(pattern))
    return matches[0] if matches else None


def enrich_inplace(_rows: List[ScanRow], _cfg: Dict[str, object]) -> None:  # v1 no-op
    # v1 CSV-only mode: do nothing
    return None

