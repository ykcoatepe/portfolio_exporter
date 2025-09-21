from __future__ import annotations

import csv
import os
import time
from typing import Any

JOURNAL_COLS = [
    "run_id",
    "symbol",
    "tier",
    "direction",
    "structure",
    "contracts",
    "expiry",
    "long_leg",
    "short_leg",
    "limit",
    "tp",
    "sl",
    "entry_trigger",
    "status",
    "status_ts",
    "result_R",
    "notes",
]


def write_journal_template(scored_rows: list[dict[str, Any]], path: str) -> None:
    """Write a journal template with status=Pending."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    run_id = time.strftime("%Y%m%d_%H%M%S")
    out: list[dict[str, Any]] = []
    for s in scored_rows:
        out.append(
            {
                "run_id": run_id,
                "symbol": s["symbol"],
                "tier": s.get("tier"),
                "direction": s.get("direction"),
                "structure": s.get("structure_template"),
                "contracts": s.get("contracts") or 0,
                "expiry": s.get("expiry"),
                "long_leg": s.get("long_strike"),
                "short_leg": s.get("short_strike"),
                "limit": s.get("debit_or_credit"),
                "tp": s.get("tp"),
                "sl": s.get("sl"),
                "entry_trigger": s.get("entry_trigger"),
                "status": "Pending",
                "status_ts": "",
                "result_R": "",
                "notes": "",
            }
        )
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=JOURNAL_COLS)
        w.writeheader()
        w.writerows(out)


def update_journal(path: str, updates: dict[str, dict[str, Any]]) -> None:
    """
    updates: { symbol: {"status": "Triggered", "status_ts": "...", "result_R": "0.5", "notes": "..."}, ... }
    Merge per symbol by latest row (same run_id); write back.
    """
    if not os.path.exists(path):
        return
    import pandas as pd

    df = pd.read_csv(path)
    for sym, vals in updates.items():
        idx = df.index[df["symbol"] == sym]
        for k, v in vals.items():
            if k in df.columns:
                df.loc[idx, k] = v
    df.to_csv(path, index=False)
