from __future__ import annotations

import itertools
import math
import os
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Tuple
from typing import Optional

import logging
import pandas as pd


log = logging.getLogger(__name__)


def get_combo_db_path() -> Path:
    """
    Resolve the current combos.db path.
    Prefers PE_DB_PATH env var if set, otherwise defaults to settings.output_dir/combos.db.
    """
    try:
        from portfolio_exporter.core.config import settings

        default_path = Path(settings.output_dir).expanduser() / "combos.db"
    except Exception:
        default_path = Path.home() / "combos.db"  # fallback if settings import fails
    db_path = Path(os.getenv("PE_DB_PATH", default_path)).expanduser()
    return db_path


def fetch_chain(symbol: str, expiry: str, strikes: List[float] | None = None) -> pd.DataFrame:
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
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (name,))
    return cur.fetchone() is not None


# --- Schema helpers ---------------------------------------------------------
def _combo_table_columns(cur: sqlite3.Cursor) -> set[str]:
    cur.execute("PRAGMA table_info(combos);")
    return {row[1] for row in cur.fetchall()}


def _detect_id_column(cur: sqlite3.Cursor) -> str:
    cols = _combo_table_columns(cur)
    if "id" in cols:
        return "id"
    if "combo_id" in cols:
        return "combo_id"
    # Fallback for legacy tables: every normal SQLite table has rowid unless created WITHOUT ROWID
    return "rowid"


def _normalize_key(v: Any) -> Any:
    # Keep type as-is for SQLite to match on equality.
    # Decode bytes/memoryview just in case.
    if isinstance(v, (bytes, bytearray, memoryview)):
        try:
            return bytes(v).decode()
        except Exception:
            return bytes(v).hex()
    return v


def _fetch_combos(cur: sqlite3.Cursor, date_from: str) -> List[Tuple[Any, str]]:
    # Use detected id column and tolerate older schemas missing opened_date
    cols = _combo_table_columns(cur)
    id_col = _detect_id_column(cur)
    has_opened = "opened_date" in cols

    if has_opened:
        try:
            cur.execute(
                f"SELECT {id_col}, underlying FROM combos WHERE opened_date >= ? OR opened_date IS NULL;",
                (date_from,),
            )
        except sqlite3.OperationalError:
            # defensive fallback if predicate fails for some reason
            cur.execute(f"SELECT {id_col}, underlying FROM combos;")
    else:
        cur.execute(f"SELECT {id_col}, underlying FROM combos;")

    rows = cur.fetchall()
    return [(_normalize_key(r[0]), r[1]) for r in rows if r and r[1]]


def _fetch_legs_for_combo(cur: sqlite3.Cursor, combo_id: Any) -> List[Dict[str, Any]]:
    """Fetch legs for a combo with flexible optional columns."""
    cur.execute("PRAGMA table_info(combo_legs);")
    cols = {r[1] for r in cur.fetchall()}
    fields = [
        c
        for c in (
            "strike",
            "right",
            "expiry",
            "qty",
            "premium",
            "price",
            "side",
        )
        if c in cols
    ]
    if not fields:
        return []
    q = f"SELECT {', '.join(fields)} FROM combo_legs WHERE combo_id=?;"
    cur.execute(q, (combo_id,))
    rows = cur.fetchall()
    legs: List[Dict[str, Any]] = []
    for r in rows:
        leg: Dict[str, Any] = {}
        for i, c in enumerate(fields):
            leg[c] = r[i]
        legs.append(leg)
    return legs


def _infer_width_from_legs(legs: list[dict]) -> Optional[float]:
    """
    Infer width based on strikes/rights when possible.
    Rules:
      - Vertical: 2 legs, same expiry/right, opposite side -> abs(strike1 - strike2)
      - Iron Condor: 4 legs, same expiry, 2 calls + 2 puts ->
          width = max(call_spread_width, put_spread_width)
      - Butterfly: 3-4 legs, same expiry, symmetric-ish ->
          width = distance between wing and body strike if identifiable,
                  else max adjacent strike diff
      - Calendar: 0.0
    Returns None if insufficient info.
    """
    if not legs or len(legs) < 2:
        return None
    strikes = []
    rights = []
    expiries = set()
    for leg in legs:
        try:
            s = float(leg.get("strike"))
            strikes.append(s)
            rights.append(str(leg.get("right", "")).upper())
            expiries.add(str(leg.get("expiry", "")))
        except Exception:
            return None
    if len(expiries) > 1:
        return 0.0 if all(r in {"C", "P"} for r in rights) else None
    n = len(legs)
    if n == 2 and len(set(rights)) == 1:
        return math.fabs(strikes[0] - strikes[1])
    if n == 4 and set(rights) == {"C", "P"}:
        call_strikes = [s for s, r in zip(strikes, rights) if r == "C"]
        put_strikes = [s for s, r in zip(strikes, rights) if r == "P"]
        if len(call_strikes) >= 2 and len(put_strikes) >= 2:
            cw = math.fabs(max(call_strikes) - min(call_strikes))
            pw = math.fabs(max(put_strikes) - min(put_strikes))
            return max(cw, pw)
    if n in (3, 4) and len(set(rights)) == 1:
        smin, smax = min(strikes), max(strikes)
        return (smax - smin) / 2.0
    return None


def _infer_credit_debit(legs: list[dict]) -> Optional[str]:
    """
    Infer Credit/Debit from premium or price * qty.
    Prefer premium if present on all legs, else price.
    signed_qty: use qty if signed, else derive from 'side'.
    """
    if not legs or len(legs) < 1:
        return None
    field = None
    if all("premium" in leg and leg["premium"] is not None for leg in legs):
        field = "premium"
    elif all("price" in leg and leg["price"] is not None for leg in legs):
        field = "price"
    else:
        return None
    total = 0.0
    for leg in legs:
        try:
            val = float(leg[field])
            qty = float(leg.get("qty", 0))
            if qty == 0 and "side" in leg:
                side = str(leg["side"]).upper()
                qty = 1.0 if side in {"SELL", "SHORT"} else -1.0 if side in {"BUY", "LONG"} else 0.0
            total += val * qty
        except Exception:
            return None
    return "Credit" if total >= 0 else "Debit"


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
    if n == 2 and same_right and len(set([l["strike"] for l in clean])) == 1 and len(set(expiries)) > 1:
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
        # Detect id column once per connection/transaction
        id_col = _detect_id_column(cur)
        if id_col == "rowid":
            logging.warning("Using rowid as combo key; consider migrating schema to include an 'id' column.")
        combos = _fetch_combos(cur, date_from)
        if not combos:
            print(f"[backfill] No combos found from {date_from}.")
            conn.close()
            return
        has_legs = _table_exists(cur, "combo_legs")
        # For parent lineage, grab all combos with expiry if present
        colnames = [r[1] for r in cur.execute("PRAGMA table_info(combos);").fetchall()]
        has_expiry = "expiry" in colnames
        all_combos_meta: Dict[Any, Dict[str, Any]] = {}
        if has_expiry:
            for cid, underlying in combos:
                cur.execute(f"SELECT expiry FROM combos WHERE {id_col} = ?;", (cid,))
                r = cur.fetchone()
                all_combos_meta[cid] = {
                    "underlying": underlying,
                    "expiry": r[0] if r else None,
                }
        updated = 0
        width_filled = 0
        cd_filled = 0
        total = 0
        for cid, underlying in combos:
            total += 1
            parent_combo_id = None
            cur.execute(
                f"SELECT width, credit_debit, type FROM combos WHERE {id_col} = ?;",
                (cid,),
            )
            row = cur.fetchone() or (None, None, None)
            orig_width, orig_cd, orig_type = row
            width, credit_debit, ctype = orig_width, orig_cd, orig_type
            if has_legs:
                legs = _fetch_legs_for_combo(cur, cid)
                if legs:
                    if ctype is None:
                        ctype, _ = _infer_type_and_width(legs)
                    if orig_width is None:
                        w = _infer_width_from_legs(legs)
                        if w is not None:
                            width = w
                            width_filled += 1
                    if orig_cd is None:
                        cd = _infer_credit_debit(legs)
                        if cd is not None:
                            credit_debit = cd
                            cd_filled += 1
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
            if ctype is not None and orig_type is None:
                sets.append("type = ?")
                vals.append(ctype)
            if width is not None and orig_width is None:
                sets.append("width = ?")
                vals.append(width)
            if credit_debit is not None and orig_cd is None:
                sets.append("credit_debit = ?")
                vals.append(credit_debit)
            if parent_combo_id is not None:
                sets.append("parent_combo_id = ?")
                vals.append(parent_combo_id)
            if sets:
                vals.append(cid)
                sql = f"UPDATE combos SET {', '.join(sets)} WHERE {id_col} = ?;"
                cur.execute(sql, tuple(vals))
                updated += 1
        conn.commit()
        log.info(
            "backfill_combos: width filled %d / %d; credit_debit filled %d / %d",
            width_filled,
            total,
            cd_filled,
            total,
        )
        print(f"✅ backfill_combos: updated {updated} / {len(combos)} combos (meta fields).")
    finally:
        conn.close()
"""Test hooks: allow monkeypatching quote_option/quote_stock on this module.
These placeholders are overwritten in tests; normal callers should import
from portfolio_exporter.core.ib instead.
"""
quote_option = None  # type: ignore
quote_stock = None  # type: ignore
