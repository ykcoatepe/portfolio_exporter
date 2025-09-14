from __future__ import annotations

from typing import Any, Dict, List
import csv
import os


def export_ib_basket(orders: List[Dict[str, Any]], path: str) -> None:
    """
    Write a BasketTrader-friendly CSV with columns:
    Symbol,SecType,Right,Strike,Expiry,Currency,Action,Quantity,OrderType,LmtPrice,TIF
    One row per leg. Currency=USD, TIF=DAY, SecType=OPT.
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    rows: List[List[Any]] = []
    for o in orders:
        sym = o.get("symbol")
        qty = int(o.get("contracts") or 0)
        exp = (o.get("expiry") or "")
        struct = (o.get("structure") or o.get("structure_template") or "").lower()
        if qty <= 0 or not sym:
            continue
        if struct == "debitcall":
            if o.get("long_leg") and o.get("short_leg"):
                rows.append([sym, "OPT", "C", _strike(o["long_leg"]), exp, "USD", "BUY", qty, "LMT", _num(o.get("limit")), "DAY"])
                rows.append([sym, "OPT", "C", _strike(o["short_leg"]), exp, "USD", "SELL", qty, "LMT", _num(o.get("limit")), "DAY"])
        elif struct in ("bearcallcredit", "bullputcredit"):
            right = "C" if "call" in struct else "P"
            if o.get("short_leg") and o.get("long_leg"):
                rows.append([sym, "OPT", right, _strike(o["short_leg"]), exp, "USD", "SELL", qty, "LMT", _num(o.get("limit")), "DAY"])
                rows.append([sym, "OPT", right, _strike(o["long_leg"]), exp, "USD", "BUY", qty, "LMT", _num(o.get("limit")), "DAY"])
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Symbol", "SecType", "Right", "Strike", "Expiry", "Currency", "Action", "Quantity", "OrderType", "LmtPrice", "TIF"])
        w.writerows(rows)


def export_ib_notes(orders: List[Dict[str, Any]], path_txt: str) -> None:
    """Write human notes with TP/SL guidance per order (OCO not in basket CSV)."""
    os.makedirs(os.path.dirname(path_txt) or ".", exist_ok=True)
    lines: List[str] = []
    for o in orders:
        lines.append(
            f"{o.get('symbol')} {o.get('structure') or o.get('structure_template')} "
            f"qty={o.get('contracts')}: TP={o.get('OCO_tp')} SL={o.get('OCO_sl')} trigger={o.get('entry_trigger')}"
        )
    with open(path_txt, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _strike(leg: Any) -> str:
    if isinstance(leg, (int, float)):
        s = f"{float(leg):.2f}"
        return s.rstrip("0").rstrip(".")
    parts = str(leg).split()
    return parts[-1]


def _num(x: Any):
    try:
        return float(x) if x is not None and x != "" else ""
    except Exception:
        return ""

