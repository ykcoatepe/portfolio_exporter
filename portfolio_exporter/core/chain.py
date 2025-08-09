from __future__ import annotations

import itertools
import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


def fetch_chain(
    symbol: str, expiry: str, strikes: List[float] | None = None
) -> pd.DataFrame:
    """Return an option chain snapshot.

    The resulting DataFrame includes columns: ``strike``, ``right``, ``mid``,
    ``bid``, ``ask``, ``delta``, ``gamma``, ``vega``, ``theta`` and ``iv``.
    """
    from .ib import quote_option, quote_stock

    if not strikes:
        spot = quote_stock(symbol)["mid"]
        strikes = [round((spot // 5 + i) * 5, 0) for i in range(-5, 6)]
    rows = []
    for strike, right in itertools.product(strikes, ["C", "P"]):
        try:
            q = quote_option(symbol, expiry, strike, right)
            q.update({"strike": strike, "right": right})
            rows.append(q)
        except ValueError:
            # strike not offered for this weekly; skip gracefully
            continue
    return pd.DataFrame(rows)


def _table_exists(cur: sqlite3.Cursor, name: str) -> bool:
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (name,)
    )
    return cur.fetchone() is not None


def _fetch_combos(cur: sqlite3.Cursor, date_from: str) -> List[Tuple[int, str]]:
    # tolerate older schemas missing opened_date
    try:
        cur.execute(
            "SELECT id, underlying FROM combos WHERE opened_date >= ? OR opened_date IS NULL;",
            (date_from,),
        )
    except sqlite3.OperationalError:
        cur.execute("SELECT id, underlying FROM combos;")
    return list(cur.fetchall())


def _fetch_legs_for_combo(cur: sqlite3.Cursor, combo_id: int) -> List[Dict[str, Any]]:
    # Expected flexible columns: strike, right, expiry, qty, premium/price (some may be missing)
    cur.execute("PRAGMA table_info(combo_legs);")
    info = cur.fetchall()
    colmap = {r[1]: True for r in info} if info else {}
    sel: List[str] = []
    for c in (
        "combo_id",
        "strike",
        "right",
        "expiry",
        "qty",
        "premium",
        "price",
    ):
        if c in colmap:
            sel.append(c)
    if not sel:
        return []
    q = f"SELECT {', '.join(sel)} FROM combo_legs WHERE combo_id=?;"
    cur.execute(q, (combo_id,))
    rows = cur.fetchall()
    res: List[Dict[str, Any]] = []
    for r in rows:
        row: Dict[str, Any] = {}
        for i, c in enumerate(sel):
            row[c] = r[i]
        res.append(row)
    return res


def _infer_type_and_width(
    legs: List[Dict[str, Any]],
) -> Tuple[Optional[str], Optional[float]]:
    """
    Heuristics:
      - calendar: 2 legs, same strike, same right, different expiry
      - butterfly: 3 legs (1:-2:1) or 4 legs with symmetric strikes and same expiry
      - iron condor: 4 legs, 2 calls + 2 puts, disjoint strike wings, same expiry
      - vertical: 2 legs, same right, same expiry, different strikes
    width:
      - condor: min(call_spread_width, put_spread_width) or largest outer-inner gap as fallback
      - butterfly: (max_strike - min_strike) / 2 if symmetric, else adjacent gap
      - vertical: abs(strike1 - strike2)
      - calendar: 0.0 (by convention; time width isn’t price width)
    """
    if not legs:
        return None, None
    # Normalize fields
    clean = []
    for l in legs:
        strike = l.get("strike")
        right = (l.get("right") or "").upper() if l.get("right") else None
        expiry = l.get("expiry")
        qty = l.get("qty", 1)
        try:
            strike = float(strike) if strike is not None else None
        except Exception:
            strike = None
        clean.append({"strike": strike, "right": right, "expiry": expiry, "qty": qty})

    n = len(clean)
    strikes = [l["strike"] for l in clean if l["strike"] is not None]
    rights = [l["right"] for l in clean if l["right"] is not None]
    expiries = [l["expiry"] for l in clean if l["expiry"] is not None]
    same_expiry = len(set(expiries)) <= 1 if expiries else True
    same_right = len(set(rights)) <= 1 if rights else False
    uniq_rights = set(rights)

    # Calendar: 2 legs, same strike & right, different expiry
    if (
        n == 2
        and same_right
        and len(set([l["strike"] for l in clean])) == 1
        and len(set(expiries)) > 1
    ):
        return "calendar", 0.0

    # Vertical: 2 legs, same right & expiry, different strikes
    if (
        n == 2
        and same_right
        and same_expiry
        and len(set([l["strike"] for l in clean if l["strike"] is not None])) == 2
    ):
        s = sorted([l["strike"] for l in clean if l["strike"] is not None])
        return "vertical", abs(s[1] - s[0]) if len(s) == 2 else None

    # Iron condor: 4 legs, 2 calls + 2 puts, same expiry (when present)
    if n == 4 and uniq_rights == {"C", "P"} and same_expiry:
        calls = sorted(
            [l for l in clean if l["right"] == "C" and l["strike"] is not None],
            key=lambda x: x["strike"],
        )
        puts = sorted(
            [l for l in clean if l["right"] == "P" and l["strike"] is not None],
            key=lambda x: x["strike"],
        )
        cw = abs(calls[-1]["strike"] - calls[0]["strike"]) if len(calls) >= 2 else None
        pw = abs(puts[-1]["strike"] - puts[0]["strike"]) if len(puts) >= 2 else None
        # choose the smaller wing width as the condor width; fallback to max gap
        if cw is not None and pw is not None:
            return "iron_condor", float(min(cw, pw))
        if strikes:
            s = sorted(strikes)
            return "iron_condor", float(max(s) - min(s))
        return "iron_condor", None

    # Butterfly: 3 or 4 legs, same expiry, symmetric strikes (rough)
    if same_expiry and n in (3, 4) and strikes:
        s = sorted(strikes)
        outer = s[-1] - s[0]
        # symmetric-ish if middle close to mean
        if len(s) >= 3:
            mid = s[len(s) // 2]
            mean = (s[0] + s[-1]) / 2.0
            if abs(mid - mean) <= max(0.01, outer * 0.05):
                return "butterfly", float(outer / 2.0)
        # fallback width = outer range / 2
        return "butterfly", float(outer / 2.0) if outer else None

    # Couldn’t classify confidently
    return None, None


def backfill_combos(db: str, date_from: str = "2023-01-01") -> None:
    """
    Practical backfill:
      - Infers 'type' and 'width' from combo_legs table if present
      - Infers 'credit_debit' if combo_legs has a premium/price column
      - Sets 'parent_combo_id' via simple roll-lineage heuristic on same underlying
    Leaves 'closed_date' unchanged (needs execution-level data to populate accurately).
    """
    db_path = os.path.expanduser(db)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        combos = _fetch_combos(cur, date_from)
        if not combos:
            print(f"[backfill] No combos found from {date_from}.")
            conn.close()
            return
        has_legs = _table_exists(cur, "combo_legs")
        # For parent lineage, grab all combos with expiry if present
        colnames = [r[1] for r in cur.execute("PRAGMA table_info(combos);").fetchall()]
        has_expiry = "expiry" in colnames
        all_combos_meta: Dict[int, Dict[str, Any]] = {}
        if has_expiry:
            for cid, underlying in combos:
                cur.execute("SELECT expiry FROM combos WHERE id = ?;", (cid,))
                r = cur.fetchone()
                all_combos_meta[cid] = {
                    "underlying": underlying,
                    "expiry": r[0] if r else None,
                }
        updated = 0
        for cid, underlying in combos:
            ctype, width = (None, None)
            credit_debit = None
            parent_combo_id = None
            if has_legs:
                legs = _fetch_legs_for_combo(cur, cid)
                if legs:
                    ctype, width = _infer_type_and_width(legs)
                    # --- credit/debit inference ---
                    prem: Optional[float] = None
                    for l in legs:
                        for prem_key in ("premium", "price"):
                            if prem_key in l and l[prem_key] is not None:
                                try:
                                    prem_val = float(l[prem_key])
                                    if prem is None:
                                        prem = 0.0
                                    prem += prem_val
                                except Exception:
                                    pass
                    if prem is not None:
                        credit_debit = "credit" if prem > 0 else "debit"
            # --- strict roll-lineage heuristic ---
            if has_expiry and all_combos_meta.get(cid, {}).get("expiry"):
                try:
                    from datetime import datetime

                    this_exp = all_combos_meta[cid]["expiry"]
                    if this_exp:
                        this_dt = datetime.fromisoformat(str(this_exp))
                        for pid, meta in all_combos_meta.items():
                            if pid == cid or not meta.get("expiry"):
                                continue
                            if meta["underlying"] != underlying:
                                continue
                            parent_dt = datetime.fromisoformat(str(meta["expiry"]))
                            gap_days = (this_dt - parent_dt).days
                            # parent must expire before this one, and within 14 days gap
                            if 0 < gap_days <= 14:
                                parent_combo_id = pid
                                break
                except Exception as e:  # pragma: no cover - defensive
                    print(f"[WARN] expiry parse failed for combo {cid}: {e}")
            # Update only if we inferred something meaningful
            sets, vals = [], []
            if ctype is not None:
                sets.append("type = ?")
                vals.append(ctype)
            if width is not None:
                sets.append("width = ?")
                vals.append(width)
            if credit_debit is not None:
                sets.append("credit_debit = ?")
                vals.append(credit_debit)
            if parent_combo_id is not None:
                sets.append("parent_combo_id = ?")
                vals.append(parent_combo_id)
            if sets:
                vals.append(cid)
                sql = f"UPDATE combos SET {', '.join(sets)} WHERE id = ?;"
                cur.execute(sql, tuple(vals))
                updated += 1
        conn.commit()
        print(
            f"✅ backfill_combos: updated {updated} / {len(combos)} combos (meta fields)."
        )
    finally:
        conn.close()
