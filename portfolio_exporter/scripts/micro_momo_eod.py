from __future__ import annotations

import argparse
import csv
import os
from typing import Any, Dict, List

from ..core.journal import update_journal
from ..core.providers import ib_provider


def _load_journal(path: str) -> List[Dict[str, Any]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_summary(path: str, rows: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    wheader = ["symbol", "status", "result_R", "exit_price", "exit_reason", "notes"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=wheader)
        w.writeheader()
        w.writerows(rows)


def _price_close(symbol: str, offline: bool) -> float | None:
    if offline:
        return None
    try:
        q = ib_provider.get_quote(symbol, {"data": {"offline": False}})
        return q.get("last") or None
    except Exception:
        return None


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser("micro-momo-eod")
    ap.add_argument("--journal", required=True)
    ap.add_argument("--out_dir", default="out")
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args(argv)

    journal = _load_journal(args.journal)
    updates: Dict[str, Dict[str, Any]] = {}
    summary: List[Dict[str, Any]] = []

    for row in journal:
        sym = row["symbol"]
        status = (row.get("status") or "").lower()
        if status not in ("pending", "triggered"):
            continue
        try:
            tp = float(row.get("tp") or 0) or None
        except Exception:
            tp = None
        try:
            sl = float(row.get("sl") or 0) or None
        except Exception:
            sl = None
        try:
            entry_price = float(row.get("limit") or 0) or None
        except Exception:
            entry_price = None
        direction = (row.get("direction") or "long").lower()
        px = _price_close(sym, args.offline)

        exit_reason = "Expired"
        exit_price = px
        result_R = ""
        if entry_price and tp and sl and px is not None:
            if direction.startswith("long"):
                if px >= tp:
                    exit_reason = "Profit"
                    exit_price = tp
                    result_R = "1.0"
                elif px <= sl:
                    exit_reason = "Stopped"
                    exit_price = sl
                    result_R = "-1.0"
                else:
                    r = (px - entry_price) / max(1e-9, (tp - entry_price))
                    result_R = f"{r:.2f}"
            else:
                if tp is not None and px <= tp:
                    exit_reason = "Profit"
                    exit_price = tp
                    result_R = "1.0"
                elif px >= (sl if sl is not None else px + 1e9):
                    exit_reason = "Stopped"
                    exit_price = sl
                    result_R = "-1.0"
                else:
                    r = (entry_price - px) / max(1e-9, (entry_price - (tp if tp is not None else entry_price - 1)))
                    result_R = f"{r:.2f}"

        updates[sym] = {
            "status": exit_reason,
            "status_ts": "",
            "result_R": result_R,
            "notes": f"EOD close px={px}" if px is not None else "EOD offline",
        }
        summary.append(
            {
                "symbol": sym,
                "status": exit_reason,
                "result_R": result_R,
                "exit_price": exit_price,
                "exit_reason": exit_reason,
                "notes": updates[sym]["notes"],
            }
        )

    update_journal(args.journal, updates)
    _write_summary(os.path.join(args.out_dir, "micro_momo_eod_summary.csv"), summary)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

