from __future__ import annotations

import datetime as _dt
import hashlib
import logging
import os
import pathlib
import sqlite3
from typing import Dict, List, Tuple, Optional

from .io import migrate_combo_schema, _ensure_writable_dir
from .config import settings

import pandas as pd

log = logging.getLogger(__name__)

# ── database setup ────────────────────────────────────────────────────────────
def _default_db_path() -> pathlib.Path:
    # Allow override via env var for tests/CI
    env_path = os.environ.get("PE_DB_PATH")
    if env_path:
        p = pathlib.Path(env_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    # Honor lightweight test mode used by CLI tests
    if os.environ.get("PE_TEST_MODE"):
        local_p = pathlib.Path.cwd() / "tmp_test_run" / "combos.db"
        local_p.parent.mkdir(parents=True, exist_ok=True)
        return local_p

    # Under pytest, prefer a repo-local temporary path to avoid sandbox issues
    if os.environ.get("PYTEST_CURRENT_TEST"):
        local_p = pathlib.Path.cwd() / "tmp_test_run" / "combos.db"
        local_p.parent.mkdir(parents=True, exist_ok=True)
        return local_p

    # Preferred location alongside other app outputs with writable fallback
    try:
        base = pathlib.Path(getattr(settings, "output_dir", "."))
    except Exception:
        base = pathlib.Path.cwd()
    outdir = _ensure_writable_dir(base)
    return outdir / "combos.db"


DB_PATH = _default_db_path()

_DDL = """
CREATE TABLE IF NOT EXISTS combos (
    combo_id TEXT PRIMARY KEY,
    ts_created TEXT,
    ts_closed TEXT,
    structure TEXT,
    underlying TEXT,
    expiry TEXT,
    type TEXT,
    width REAL,
    credit_debit REAL,
    parent_combo_id TEXT,
    closed_date TEXT
);
CREATE TABLE IF NOT EXISTS legs (
    combo_id TEXT,
    conid INTEGER,
    strike REAL,
    right TEXT,
    PRIMARY KEY(combo_id, conid)
);
"""


def _db() -> sqlite3.Connection:
    try:
        conn = sqlite3.connect(DB_PATH)
    except Exception:
        # Last-resort fallback to local tmp if prior path became unwritable
        fallback = (_ensure_writable_dir(pathlib.Path.cwd() / "tmp_test_run") / "combos.db")
        conn = sqlite3.connect(fallback)
    conn.executescript(_DDL)
    migrate_combo_schema(conn)
    return conn


# ---------- util helpers --------------------------------------------------
def _hash_combo(conids: List[int]) -> str:
    h = hashlib.sha256()
    for cid in sorted(conids):
        h.update(str(cid).encode())
    return h.hexdigest()[:16]


# ---------- public API ----------------------------------------------------
def detect_combos(pos_df: pd.DataFrame, mode: str = "all") -> pd.DataFrame:
    """Group legs into combos and persist mapping.

    ``pos_df`` must be indexed by ``conId`` and include the following columns:
    ``underlying``, ``qty``, ``right``, ``strike``, ``expiry``,
    ``delta``, ``gamma``, ``vega`` and ``theta``.

    Returns a DataFrame with one row per combo summarising the greeks and
    including the list of legs.  ``mode`` may be ``"simple"`` to only detect
    verticals and straddles or ``"all"`` to include calendars, condors and
    butterflies.
    """

    if "right" not in pos_df.columns:
        pos_df["right"] = pd.NA

    combos: List[Dict] = []
    used: set[int] = set()

    for _, sub in pos_df.groupby("underlying"):
        if mode == "all":
            combos.extend(_match_calendar(sub, used))
            combos.extend(_match_condor(sub, used))
            combos.extend(_match_butterfly(sub, used))

        # verticals
        for idx, leg in sub.iterrows():
            if idx in used or leg["right"] not in {"C", "P"}:
                continue
            opp = sub[
                (sub["expiry"] == leg["expiry"])
                & (sub["right"] == leg["right"])
                & (sub["qty"] == -leg["qty"])
            ]
            opp = opp[opp.index != idx]
            if len(opp) == 1:
                other = opp.iloc[0]
                legs_idx = [idx, other.name]
                used.update(legs_idx)
                width = _calc_width(pos_df.loc[legs_idx])
                combos.append(
                    _row(
                        "VertCall" if leg["right"] == "C" else "VertPut",
                        pos_df.loc[legs_idx],
                        "vertical",
                        width,
                    )
                )

        # straddles
        for conids in _pair_same_strike(sub, used):
            used.update(conids)
            combos.append(_row("Straddle", pos_df.loc[conids], "straddle", 0.0))

    for idx in pos_df.index.difference(used):
        combos.append(_row("Single", pos_df.loc[[idx]], "single"))

    combo_df = pd.DataFrame(combos)
    if combo_df.empty:
        combo_df = pd.DataFrame(
            columns=[
                "combo_id",
                "structure",
                "underlying",
                "expiry",
                "qty",
                "delta",
                "gamma",
                "vega",
                "theta",
                "type",
                "width",
                "credit_debit",
                "parent_combo_id",
                "closed_date",
                "legs",
            ]
        ).set_index("combo_id")
    else:
        combo_df = combo_df.set_index("combo_id")
    _sync_with_db(combo_df, pos_df)
    return combo_df


def _normalize_positions_df(df: pd.DataFrame) -> pd.DataFrame:
    import pandas as pd
    import numpy as np

    if df is None or df.empty:
        return pd.DataFrame(columns=[
            "underlying","expiry","right","strike","qty","secType"
        ])

    out = df.copy()

    # --- column presence / aliases ---
    # Accept common variants and map into canonical set
    rename_map = {}
    if "position" in out.columns and "qty" not in out.columns:
        rename_map["position"] = "qty"
    if "symbol" in out.columns and "underlying" not in out.columns:
        # use symbol as a fallback only for stocks; options carry 'underlying'
        pass
    if rename_map:
        out = out.rename(columns=rename_map)

    # ensure conId column presence
    if "conId" not in out.columns:
        out["conId"] = pd.NA
    for col in ["underlying","expiry","right","strike","qty","secType","conId"]:
        if col not in out.columns:
            out[col] = np.nan

    # --- underlying fallback ---
    # if underlying is blank but symbol present, fill with symbol
    if "symbol" in out.columns:
        mask_u = out["underlying"].isna() | (out["underlying"].astype(str).str.strip() == "")
        out.loc[mask_u, "underlying"] = out.loc[mask_u, "symbol"]

    # --- normalize right to C/P ---
    def norm_right(x):
        if x is None:
            return np.nan
        s = str(x).strip().upper()
        if s in ("C","CALL"): return "C"
        if s in ("P","PUT"):  return "P"
        return np.nan
    out["right"] = out["right"].apply(norm_right)

    # --- numeric coercions ---
    out["strike"] = pd.to_numeric(out["strike"], errors="coerce")
    out["qty"] = pd.to_numeric(out["qty"], errors="coerce")
    # conId may be a string – coerce when possible
    try:
        out["conId"] = pd.to_numeric(out["conId"], errors="coerce").astype("Int64")
    except Exception:
        pass

    # Drop rows without meaningful qty (0/NaN) for option legs
    out = out[~out["qty"].isna() & (out["qty"] != 0)]

    # --- expiry parsing ---
    # Accept YYYYMM / YYYYMMDD / YYYY-MM-DD / YYYY/MM/DD etc.
    def parse_exp(s):
        if s is None:
            return ""
        t = str(s).strip()
        if t == "":
            return ""
        # try pandas parsing first
        try:
            dt = pd.to_datetime(t, errors="raise", utc=False)
            return dt.strftime("%Y%m%d")
        except Exception:
            pass
        # compact numeric forms
        t2 = t.replace("-","").replace("/","").replace(" ","")
        if t2.isdigit():
            if len(t2) >= 8:
                return t2[:8]
            if len(t2) == 6:
                return t2
        return t  # last resort, leave as-is

    out["expiry"] = out["expiry"].apply(parse_exp)

    # Synthesize conId for missing rows so we can persist legs
    def _synth_conid(row):
        try:
            val = row.get("conId")
            if pd.notna(val):
                return int(val)
        except Exception:
            pass
        key = f"{row.get('underlying','')}|{row.get('expiry','')}|{row.get('right','')}|{row.get('strike','')}"
        import hashlib as _hl
        # Use 32-bit slice and negate to avoid colliding with real conIds
        v = int.from_bytes(_hl.sha1(key.encode()).digest()[:4], "big")
        return -int(v)

    try:
        out["conId"] = out.apply(_synth_conid, axis=1).astype("Int64")
    except Exception:
        pass

    # Keep only columns the detector needs
    out = out[["underlying","expiry","right","strike","qty","secType","conId"]].copy()

    # Focus detection on option-like instruments only
    out = out[out["secType"].isin(["OPT", "FOP"])].copy()

    # Optional debug dump
    import os
    if os.getenv("PE_DEBUG_COMBOS") == "1":
        try:
            from portfolio_exporter.core import io as io_core, config as config_core
            io_core.save(out, "positions_normalized_debug", "csv", config_core.settings.output_dir)
        except Exception:
            pass

    return out.reset_index(drop=True)


def detect_from_positions(df_positions: pd.DataFrame, min_abs_qty: int = 1) -> pd.DataFrame:
    """Greedy live detector for true multi‑leg combos.

    - Normalizes the positions DataFrame.
    - Consumes legs into combos in priority: verticals, butterflies, iron condors, calendars.
    - Returns only multi‑leg structures; never emits singles.
    """

    if df_positions is None or df_positions.empty:
        return pd.DataFrame(
            columns=[
                "underlying",
                "expiry",
                "structure",
                "type",
                "legs",
                "legs_n",
                "width",
                "credit_debit",
                "parent_combo_id",
                "closed_date",
            ]
        )

    norm = _normalize_positions_df(df_positions)
    # Derive helpers expected by the detector
    if not {"abs_qty", "side"}.issubset(norm.columns):
        try:
            norm["abs_qty"] = norm["qty"].abs().astype(int)
            norm["side"] = norm["qty"].apply(lambda q: "long" if float(q) > 0 else "short")
        except Exception:
            norm["abs_qty"] = 0
            norm["side"] = ""
    norm = norm[norm["abs_qty"] >= int(min_abs_qty)].copy()
    if norm.empty:
        # Optional debug: emit a diagnostic when no option rows found
        import os
        if os.getenv("PE_DEBUG_COMBOS") == "1":
            try:
                from portfolio_exporter.core import io as io_core, config as config_core
                # Build minimal diagnostic frame
                diag = pd.DataFrame(
                    [{
                        "reason": "no_option_rows_after_normalization",
                        "total_input_rows": int(len(df_positions) if df_positions is not None else 0),
                    }]
                )
                io_core.save(diag, "combos_diag_debug", "csv", config_core.settings.output_dir)
            except Exception:
                pass
        return pd.DataFrame(
            columns=[
                "underlying",
                "expiry",
                "structure",
                "type",
                "legs",
                "legs_n",
                "width",
                "credit_debit",
                "parent_combo_id",
                "closed_date",
            ]
        )

    # Track remaining lots per row
    remaining = norm["abs_qty"].to_dict()

    rows: List[Dict[str, object]] = []

    # Per-underlying processing
    totals = {"vertical": 0, "iron condor": 0, "butterfly": 0, "calendar": 0}
    # Build equity positions lookup for covered-call detection
    eq_lookup: Dict[str, Dict[str, object]] = {}
    try:
        eq_src = df_positions.copy()
        if "underlying" not in eq_src.columns and "symbol" in eq_src.columns:
            eq_src["underlying"] = eq_src["symbol"]
        eq_src = eq_src[eq_src.get("secType").isin(["STK", "ETF"])]
        if not eq_src.empty:
            for u, g in eq_src.groupby("underlying"):
                try:
                    total_shares = float(pd.to_numeric(g["qty"], errors="coerce").fillna(0).sum())
                except Exception:
                    total_shares = 0.0
                # pick a representative conId for the stock row (or synthesize)
                conid = None
                try:
                    cval = g.get("conId")
                    if cval is not None and not pd.isna(cval).all():
                        conid = int(pd.to_numeric(cval, errors="coerce").dropna().iloc[0])
                except Exception:
                    conid = None
                if conid is None:
                    key = f"{u}|STK"
                    v = int.from_bytes(hashlib.sha1(key.encode()).digest()[:4], "big")
                    conid = -int(v)
                eq_lookup[str(u)] = {"shares": total_shares, "conId": int(conid)}
    except Exception:
        eq_lookup = {}

    for u_sym, u_df in norm.groupby("underlying"):
        u_df = u_df.sort_values(["expiry", "right", "strike"]).copy()
        # Map row index -> conId for leg persistence
        try:
            row_conid = {int(i): int(u_df.loc[i, "conId"]) for i in u_df.index}
        except Exception:
            row_conid = {int(i): None for i in u_df.index}

        # Index helpers
        def _legs_for(exp: str, right: str) -> List[int]:
            sub = u_df[(u_df["expiry"] == exp) & (u_df["right"] == right)]
            # Sorted by strike for verticals/butterflies
            return list(sub.sort_values("strike").index)

        def _legs_for_strike(strike: float, right: str) -> List[int]:
            sub = u_df[(u_df["strike"] == strike) & (u_df["right"] == right)]
            return list(sub.sort_values("expiry").index)

        # ── 1) Verticals (same expiry, same right) ──────────────────────
        vertical_records: List[Tuple[str, str, float, float, int, List[int]]] = []
        # (expiry, right, k_low, k_high, matched_qty, [row_i,row_j])
        for (exp, right), grp in u_df.groupby(["expiry", "right"]):
            idxs = list(grp.sort_values("strike").index)
            # Separate longs/shorts
            longs = [i for i in idxs if remaining.get(i, 0) > 0 and u_df.loc[i, "side"] == "long"]
            shorts = [i for i in idxs if remaining.get(i, 0) > 0 and u_df.loc[i, "side"] == "short"]
            if not longs or not shorts:
                continue
            # Greedy pairing preference by option type
            # For calls prefer long lowerK with short higherK; for puts prefer short higherK with long lowerK.
            def _strike(i: int) -> float:
                return float(u_df.loc[i, "strike"])

            longs_sorted = sorted(longs, key=_strike)
            shorts_sorted = sorted(shorts, key=_strike)

            # Two-pointer scan over strikes
            li, si = 0, 0
            while li < len(longs_sorted) and si < len(shorts_sorted):
                i_long = longs_sorted[li]
                i_short = shorts_sorted[si]
                kL, kS = _strike(i_long), _strike(i_short)

                # Enforce different strikes
                if kL == kS:
                    # Advance the one with smaller remaining to find off-strike pair
                    if remaining[i_long] <= remaining[i_short]:
                        li += 1
                    else:
                        si += 1
                    continue

                prefer = (right == "C" and kL < kS) or (right == "P" and kS > kL)
                alt = (right == "C" and kL > kS) or (right == "P" and kS < kL)
                if not (prefer or alt):
                    # Move pointers towards valid orientation
                    if right == "C":
                        # want kL < kS ideally
                        if kL < kS:
                            pass  # valid but caught by prefer
                        # adjust whichever is out of place
                        if kL >= kS:
                            si += 1
                            continue
                    else:  # Puts prefer kS > kL
                        if kS <= kL:
                            li += 1
                            continue

                m = min(remaining[i_long], remaining[i_short])
                if m <= 0:
                    if remaining[i_long] <= 0:
                        li += 1
                    if remaining[i_short] <= 0:
                        si += 1
                    continue
                k_low, k_high = (kL, kS) if kL < kS else (kS, kL)
                vertical_records.append((exp, right, k_low, k_high, m, [i_long, i_short]))
                remaining[i_long] -= m
                remaining[i_short] -= m
                if remaining[i_long] <= 0:
                    li += 1
                if remaining[i_short] <= 0:
                    si += 1

        # ── 2) Butterflies (same expiry, same right, 1:-2:1) ────────────
        butterfly_records: List[Tuple[str, str, float, float, float, int, List[int]]] = []
        for (exp, right), grp in u_df.groupby(["expiry", "right"]):
            g = grp.sort_values("strike")
            strikes = list(g["strike"].unique())
            if len(strikes) < 3:
                continue
            # Build per-strike remaining longs/shorts counts and row indices
            rows_by_strike = {k: list(g[g["strike"] == k].index) for k in strikes}
            def _avail(side: str, row_ids: List[int]) -> int:
                return sum(remaining[i] for i in row_ids if remaining.get(i, 0) > 0 and u_df.loc[i, "side"] == side)

            for i in range(1, len(strikes) - 1):
                k1, k2, k3 = strikes[i - 1], strikes[i], strikes[i + 1]
                rows1, rows2, rows3 = rows_by_strike[k1], rows_by_strike[k2], rows_by_strike[k3]
                # Long wings, short body
                lots1 = _avail("long", rows1)
                lots2_short = _avail("short", rows2)
                lots3 = _avail("long", rows3)
                m1 = min(lots1, lots2_short // 2, lots3)
                if m1 > 0:
                    # Consume greedily across rows
                    used_rows: List[int] = []
                    need = {"long@k1": m1, "short@k2": 2 * m1, "long@k3": m1}
                    for rid in rows1:
                        if need["long@k1"] == 0:
                            break
                        if u_df.loc[rid, "side"] == "long" and remaining.get(rid, 0) > 0:
                            take = min(remaining[rid], need["long@k1"])
                            remaining[rid] -= take
                            if take > 0:
                                used_rows.append(rid)
                                need["long@k1"] -= take
                    for rid in rows2:
                        if need["short@k2"] == 0:
                            break
                        if u_df.loc[rid, "side"] == "short" and remaining.get(rid, 0) > 0:
                            take = min(remaining[rid], need["short@k2"])
                            remaining[rid] -= take
                            if take > 0:
                                used_rows.append(rid)
                                need["short@k2"] -= take
                    for rid in rows3:
                        if need["long@k3"] == 0:
                            break
                        if u_df.loc[rid, "side"] == "long" and remaining.get(rid, 0) > 0:
                            take = min(remaining[rid], need["long@k3"])
                            remaining[rid] -= take
                            if take > 0:
                                used_rows.append(rid)
                                need["long@k3"] -= take
                    width = float(min(k2 - k1, k3 - k2))
                    butterfly_records.append((exp, right, k1, k2, k3, m1, used_rows))
                    continue
                # Short wings, long body (short butterfly)
                lots1s = _avail("short", rows1)
                lots2l = _avail("long", rows2)
                lots3s = _avail("short", rows3)
                m2 = min(lots1s, lots2l // 2, lots3s)
                if m2 > 0:
                    used_rows = []
                    need = {"short@k1": m2, "long@k2": 2 * m2, "short@k3": m2}
                    for rid in rows1:
                        if need["short@k1"] == 0:
                            break
                        if u_df.loc[rid, "side"] == "short" and remaining.get(rid, 0) > 0:
                            take = min(remaining[rid], need["short@k1"])
                            remaining[rid] -= take
                            if take > 0:
                                used_rows.append(rid)
                                need["short@k1"] -= take
                    for rid in rows2:
                        if need["long@k2"] == 0:
                            break
                        if u_df.loc[rid, "side"] == "long" and remaining.get(rid, 0) > 0:
                            take = min(remaining[rid], need["long@k2"])
                            remaining[rid] -= take
                            if take > 0:
                                used_rows.append(rid)
                                need["long@k2"] -= take
                    for rid in rows3:
                        if need["short@k3"] == 0:
                            break
                        if u_df.loc[rid, "side"] == "short" and remaining.get(rid, 0) > 0:
                            take = min(remaining[rid], need["short@k3"])
                            remaining[rid] -= take
                            if take > 0:
                                used_rows.append(rid)
                                need["short@k3"] -= take
                    width = float(min(k2 - k1, k3 - k2))
                    butterfly_records.append((exp, right, k1, k2, k3, m2, used_rows))

        # ── 3) Iron condors (pair one call vertical with one put vertical) ──
        # Aggregate vertical units by expiry
        condor_records: List[Tuple[str, float, int, List[int]]] = []
        # Map expiry -> lists of (width, qty, rows)
        from collections import defaultdict

        exp_call: Dict[str, List[Tuple[float, int, List[int]]]] = defaultdict(list)
        exp_put: Dict[str, List[Tuple[float, int, List[int]]]] = defaultdict(list)
        for exp, right, k1, k2, q, rows_used in vertical_records:
            width = float(abs(k2 - k1))
            rec = (width, q, rows_used)
            if right == "C":
                exp_call[exp].append(rec)
            else:
                exp_put[exp].append(rec)

        # Greedy pairing by matched qty and same orientation (both credit or both debit)
        vertical_keep: List[Tuple[str, str, float, float, int, List[int]]] = []
        def _vert_orient(row_ids: List[int], right_val: str) -> str:
            if len(row_ids) != 2:
                return "unknown"
            i1, i2 = row_ids[0], row_ids[1]
            k1, k2 = float(u_df.loc[i1, "strike"]), float(u_df.loc[i2, "strike"])
            s1, s2 = str(u_df.loc[i1, "side"]), str(u_df.loc[i2, "side"])  # long/short
            # Identify which strike is long vs short
            long_k = k1 if s1 == "long" else k2
            short_k = k1 if s1 == "short" else k2
            if right_val == "C":
                return "debit" if long_k < short_k else "credit"
            else:  # P
                return "debit" if long_k > short_k else "credit"
        for exp in set(list(exp_call.keys()) + list(exp_put.keys())):
            calls = exp_call.get(exp, [])
            puts = exp_put.get(exp, [])
            # Sort by width for stable pairing
            calls.sort(key=lambda t: t[0])
            puts.sort(key=lambda t: t[0])
            # Attempt to pair per orientation
            for orient in ("credit", "debit"):
                ci, pi = 0, 0
                while ci < len(calls) and pi < len(puts):
                    c_w, c_q, c_rows = calls[ci]
                    p_w, p_q, p_rows = puts[pi]
                    if _vert_orient(c_rows, "C") != orient:
                        ci += 1
                        continue
                    if _vert_orient(p_rows, "P") != orient:
                        pi += 1
                        continue
                    m = min(c_q, p_q)
                    if m <= 0:
                        if c_q <= 0:
                            ci += 1
                        if p_q <= 0:
                            pi += 1
                        continue
                    width = float(min(c_w, p_w))
                    condor_records.append((exp, width, m, c_rows + p_rows))
                    # Reduce vertical lots and advance when exhausted
                    calls[ci] = (c_w, c_q - m, c_rows)
                    puts[pi] = (p_w, p_q - m, p_rows)
                    if calls[ci][1] <= 0:
                        ci += 1
                    if puts[pi][1] <= 0:
                        pi += 1
            # Any residual verticals remain as vertical structures (check all entries)
            for c_w, c_q, c_rows in calls:
                if c_q > 0:
                    ks = [float(u_df.loc[i, "strike"]) for i in c_rows]
                    k1, k2 = min(ks), max(ks)
                    vertical_keep.append((exp, "C", k1, k2, c_q, c_rows))
            for p_w, p_q, p_rows in puts:
                if p_q > 0:
                    ks = [float(u_df.loc[i, "strike"]) for i in p_rows]
                    k1, k2 = min(ks), max(ks)
                    vertical_keep.append((exp, "P", k1, k2, p_q, p_rows))

        # Compose rows for this underlying
        # Helper: classify vertical orientation
        def _classify_vertical(right_val: str, row_ids: List[int]) -> str:
            if len(row_ids) != 2:
                return "vertical"
            i1, i2 = row_ids[0], row_ids[1]
            s1, s2 = float(u_df.loc[i1, "strike"]), float(u_df.loc[i2, "strike"])
            side1, side2 = str(u_df.loc[i1, "side"]), str(u_df.loc[i2, "side"])
            long_k = s1 if side1 == "long" else s2
            short_k = s1 if side1 == "short" else s2
            if right_val == "C":
                return "bull call" if long_k < short_k else "bear call"
            else:  # P
                return "bull put" if long_k < short_k else "bear put"

        # Verticals (residual)
        for exp, right, k1, k2, q, used_rows in vertical_keep:
            vname = _classify_vertical(right, used_rows)
            # Ratio labeling: if total longs != total shorts in this (exp,right) group, mark as ratio
            grp_all = u_df[(u_df["expiry"] == exp) & (u_df["right"] == right)]
            try:
                tot_long = int(grp_all.loc[grp_all["side"] == "long", "abs_qty"].sum())
                tot_short = int(grp_all.loc[grp_all["side"] == "short", "abs_qty"].sum())
            except Exception:
                tot_long = tot_short = q
            is_ratio = tot_long != tot_short
            ratio_suffix = ""
            try:
                a, b = sorted([tot_long, tot_short])
                if is_ratio and a > 0 and b > 0:
                    ratio_suffix = f" {a}x{b}"
            except Exception:
                pass
            leg_ids = [row_conid.get(int(r)) for r in used_rows if int(r) in row_conid]
            rows.append(
                {
                    "underlying": u_sym,
                    "expiry": exp,
                    "structure": (vname + ratio_suffix) if is_ratio else vname,
                    "type": "ratio" if is_ratio else "vertical",
                    "legs": leg_ids,
                    "legs_n": len([x for x in leg_ids if x is not None]),
                    "width": float(abs(k2 - k1)),
                    "credit_debit": None,
                    "parent_combo_id": None,
                    "closed_date": None,
                }
            )
            totals["vertical"] += 1

        # Butterflies
        for exp, right, k1, k2, k3, q, used_rows in butterfly_records:
            leg_ids = [row_conid.get(int(r)) for r in used_rows if int(r) in row_conid]
            rows.append(
                {
                    "underlying": u_sym,
                    "expiry": exp,
                    "structure": "butterfly",
                    "type": "butterfly",
                    "legs": leg_ids,
                    "legs_n": len([x for x in leg_ids if x is not None]),
                    "width": float(min(k2 - k1, k3 - k2)),
                    "credit_debit": None,
                    "parent_combo_id": None,
                    "closed_date": None,
                }
            )
            totals["butterfly"] += 1

        # Iron condors
        for exp, width, q, used_rows in condor_records:
            leg_ids = [row_conid.get(int(r)) for r in used_rows if int(r) in row_conid]
            rows.append(
                {
                    "underlying": u_sym,
                    "expiry": exp,
                    "structure": "iron condor",
                    "type": "iron condor",
                    "legs": leg_ids,
                    "legs_n": len([x for x in leg_ids if x is not None]),
                    "width": float(width),
                    "credit_debit": None,
                    "parent_combo_id": None,
                    "closed_date": None,
                }
            )
            totals["iron condor"] += 1

        # ── 4) Calendars (across expiries, same strike+right, opposite sides) ──
        used_for_calendar: set[int] = set()
        for (strike, right), grp in u_df.groupby(["strike", "right"]):
            # Build list of rows with remaining > 0
            cand = [i for i in grp.index if remaining.get(i, 0) > 0]
            if len(cand) < 2:
                continue
            # Sort by expiry
            cand_sorted = sorted(cand, key=lambda i: (u_df.loc[i, "expiry"]))
            # Try to pair earliest vs later with opposite sides
            for i in range(len(cand_sorted) - 1):
                a = cand_sorted[i]
                if remaining.get(a, 0) <= 0:
                    continue
                for j in range(i + 1, len(cand_sorted)):
                    b = cand_sorted[j]
                    if remaining.get(b, 0) <= 0:
                        continue
                    if u_df.loc[a, "side"] == u_df.loc[b, "side"]:
                        continue
                    m = min(remaining[a], remaining[b])
                    if m <= 0:
                        continue
                    exp_use = max(u_df.loc[a, "expiry"], u_df.loc[b, "expiry"])  # later expiry
                    remaining[a] -= m
                    remaining[b] -= m
                    used_for_calendar.update([a, b])
                    leg_ids = [row_conid.get(int(a)), row_conid.get(int(b))]
                    rows.append(
                        {
                            "underlying": u_sym,
                            "expiry": exp_use,
                            "structure": "calendar",
                            "type": "calendar",
                            "legs": leg_ids,
                            "legs_n": len([x for x in leg_ids if x is not None]),
                            "width": 0.0,
                            "credit_debit": None,
                            "parent_combo_id": None,
                            "closed_date": None,
                        }
                    )
                    totals["calendar"] += 1

        # ── 5) Diagonals (across expiries, same right, different strikes, opposite sides) ──
        for right in ["C", "P"]:
            grp = u_df[u_df["right"] == right].sort_values(["strike", "expiry"])  # stable order
            if grp.empty:
                continue
            idxs = [i for i in grp.index if remaining.get(i, 0) > 0]
            for i in range(len(idxs)):
                a = idxs[i]
                if remaining.get(a, 0) <= 0:
                    continue
                for j in range(i + 1, len(idxs)):
                    b = idxs[j]
                    if remaining.get(b, 0) <= 0:
                        continue
                    if u_df.loc[a, "side"] == u_df.loc[b, "side"]:
                        continue
                    # Require different expiries for diagonals; equal-expiry pairs are verticals/calendars
                    if str(u_df.loc[a, "expiry"]) == str(u_df.loc[b, "expiry"]):
                        continue
                    # skip equal-strike pairs (those are calendars handled earlier)
                    if float(u_df.loc[a, "strike"]) == float(u_df.loc[b, "strike"]):
                        continue
                    m = min(remaining[a], remaining[b])
                    if m <= 0:
                        continue
                    exp_use = max(u_df.loc[a, "expiry"], u_df.loc[b, "expiry"])  # later expiry
                    width = abs(float(u_df.loc[a, "strike"]) - float(u_df.loc[b, "strike"]))
                    remaining[a] -= m
                    remaining[b] -= m
                    leg_ids = [row_conid.get(int(a)), row_conid.get(int(b))]
                    rows.append(
                        {
                            "underlying": u_sym,
                            "expiry": exp_use,
                            "structure": "diagonal",
                            "type": "diagonal",
                            "legs": leg_ids,
                            "legs_n": len([x for x in leg_ids if x is not None]),
                            "width": float(width),
                            "credit_debit": None,
                            "parent_combo_id": None,
                            "closed_date": None,
                        }
                    )

        # ── 6) Straddles (same expiry & strike, call+put, same side) ──
        for exp, grp in u_df.groupby("expiry"):
            strikes = sorted(grp["strike"].unique())
            for k in strikes:
                gk = grp[grp["strike"] == k]
                for side in ["long", "short"]:
                    c_rows = [i for i in gk.index if u_df.loc[i, "right"] == "C" and u_df.loc[i, "side"] == side and remaining.get(i, 0) > 0]
                    p_rows = [i for i in gk.index if u_df.loc[i, "right"] == "P" and u_df.loc[i, "side"] == side and remaining.get(i, 0) > 0]
                    if not c_rows or not p_rows:
                        continue
                    c_lots = sum(remaining[i] for i in c_rows)
                    p_lots = sum(remaining[i] for i in p_rows)
                    m_target = min(c_lots, p_lots)
                    if m_target <= 0:
                        continue
                    used_rows: List[int] = []
                    # consume from first available rows
                    for rid in c_rows:
                        if m_target <= 0:
                            break
                        take = min(remaining.get(rid, 0), m_target)
                        if take > 0:
                            remaining[rid] -= take
                            used_rows.append(rid)
                            m_target -= take
                    m2 = min(sum(remaining[i] for i in p_rows), min(c_lots, p_lots))
                    for rid in p_rows:
                        if m2 <= 0:
                            break
                        take = min(remaining.get(rid, 0), m2)
                        if take > 0:
                            remaining[rid] -= take
                            used_rows.append(rid)
                            m2 -= take
                    if used_rows:
                        leg_ids = [row_conid.get(int(r)) for r in used_rows if int(r) in row_conid]
                        rows.append(
                            {
                                "underlying": u_sym,
                                "expiry": exp,
                                "structure": "straddle",
                                "type": "straddle",
                                "legs": leg_ids,
                                "legs_n": len([x for x in leg_ids if x is not None]),
                                "width": 0.0,
                                "credit_debit": None,
                                "parent_combo_id": None,
                                "closed_date": None,
                            }
                        )

        # ── 7) Strangles (same expiry, different strikes, call+put, same side) ──
        for exp, grp in u_df.groupby("expiry"):
            calls = grp[grp["right"] == "C"].sort_values("strike")
            puts = grp[grp["right"] == "P"].sort_values("strike")
            for side in ["long", "short"]:
                ci, pi = 0, 0
                c_idx = [i for i in calls.index if u_df.loc[i, "side"] == side and remaining.get(i, 0) > 0]
                p_idx = [i for i in puts.index if u_df.loc[i, "side"] == side and remaining.get(i, 0) > 0]
                while ci < len(c_idx) and pi < len(p_idx):
                    ic, ip = c_idx[ci], p_idx[pi]
                    kc, kp = float(u_df.loc[ic, "strike"]), float(u_df.loc[ip, "strike"])
                    if kc == kp:  # straddle handled already
                        # advance the one with less remaining
                        if remaining.get(ic, 0) <= remaining.get(ip, 0):
                            ci += 1
                        else:
                            pi += 1
                        continue
                    m = min(remaining.get(ic, 0), remaining.get(ip, 0))
                    if m <= 0:
                        if remaining.get(ic, 0) <= 0:
                            ci += 1
                        if remaining.get(ip, 0) <= 0:
                            pi += 1
                        continue
                    remaining[ic] -= m
                    remaining[ip] -= m
                    leg_ids = [row_conid.get(int(ic)), row_conid.get(int(ip))]
                    rows.append(
                        {
                            "underlying": u_sym,
                            "expiry": exp,
                            "structure": "strangle",
                            "type": "strangle",
                            "legs": leg_ids,
                            "legs_n": len([x for x in leg_ids if x is not None]),
                            "width": float(abs(kc - kp)),
                            "credit_debit": None,
                            "parent_combo_id": None,
                            "closed_date": None,
                        }
                    )
                    if remaining.get(ic, 0) <= 0:
                        ci += 1
                    if remaining.get(ip, 0) <= 0:
                        pi += 1

        # ── 8) Covered calls (short calls paired with long stock) ──
        stock_info = eq_lookup.get(str(u_sym))
        if stock_info and float(stock_info.get("shares", 0)) > 0:
            shares_avail = float(stock_info.get("shares", 0))
            stk_conid = int(stock_info.get("conId"))
            shorts = [i for i in u_df.index if u_df.loc[i, "right"] == "C" and u_df.loc[i, "side"] == "short" and remaining.get(i, 0) > 0]
            for rid in shorts:
                lots_cover = int(min(remaining.get(rid, 0), shares_avail // 100))
                if lots_cover <= 0:
                    continue
                remaining[rid] -= lots_cover
                shares_avail -= lots_cover * 100
                leg_ids = [row_conid.get(int(rid)), stk_conid]
                rows.append(
                    {
                        "underlying": u_sym,
                        "expiry": u_df.loc[rid, "expiry"],
                        "structure": "covered call",
                        "type": "covered",
                        "legs": leg_ids,
                        "legs_n": len([x for x in leg_ids if x is not None]),
                        "width": 0.0,
                        "credit_debit": None,
                        "parent_combo_id": None,
                        "closed_date": None,
                    }
                )

        # Per-underlying log
        log.info(
            "Live combos [%s]: %s vertical, %s condor, %s butterfly, %s calendar",
            u_sym,
            totals["vertical"],
            totals["iron condor"],
                totals["butterfly"],
                totals["calendar"],
            )

    # Grand total log
    grand_total = sum(totals.values())
    log.info(
        "Live combos total: %s vertical, %s condor, %s butterfly, %s calendar; total=%s",
        totals["vertical"],
        totals["iron condor"],
        totals["butterfly"],
        totals["calendar"],
        grand_total,
    )

    if not rows:
        # Optional debug: emit per (underlying, expiry, right) sign/strike availability
        import os
        if os.getenv("PE_DEBUG_COMBOS") == "1":
            try:
                from portfolio_exporter.core import io as io_core, config as config_core
                def _signs(s: pd.Series) -> tuple[bool, bool]:
                    return (bool((s > 0).any()), bool((s < 0).any()))
                # Group diagnostics
                grp = (
                    norm.groupby(["underlying", "expiry", "right"], dropna=False)
                    .agg(
                        rows=("qty", "size"),
                        longs=("qty", lambda s: int((s > 0).sum())),
                        shorts=("qty", lambda s: int((s < 0).sum())),
                        strikes_unique=("strike", lambda s: int(pd.Series(s).nunique()))
                    )
                    .reset_index()
                )
                if grp.empty:
                    grp = pd.DataFrame([
                        {
                            "underlying": "",
                            "expiry": "",
                            "right": "",
                            "rows": 0,
                            "longs": 0,
                            "shorts": 0,
                            "strikes_unique": 0,
                        }
                    ])
                io_core.save(grp, "combos_diag_debug", "csv", config_core.settings.output_dir)
            except Exception:
                pass
        return pd.DataFrame(
            columns=[
                "underlying",
                "expiry",
                "structure",
                "type",
                "legs",
                "width",
                "credit_debit",
                "parent_combo_id",
                "closed_date",
            ]
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "underlying",
                "expiry",
                "structure",
                "structure_label",
                "type",
                "legs",
                "legs_n",
                "width",
                "credit_debit",
                "parent_combo_id",
                "closed_date",
            ]
        )
    # Ensure required columns exist and are typed consistently
    out = pd.DataFrame(rows)
    if "structure_label" not in out.columns:
        out["structure_label"] = out.get("structure", "")
    # Coerce lists for legs and count into legs_n if missing
    if "legs_n" not in out.columns:
        out["legs_n"] = out.get("legs").apply(lambda v: len(v) if isinstance(v, (list, tuple)) else 0)
    return out


# ---------- helpers -------------------------------------------------------
def _row(
    structure: str,
    legs_df: pd.DataFrame,
    type_: str,
    width: float | None = None,
    credit_debit: float | None = None,
) -> Dict:
    combo_id = _hash_combo(list(legs_df.index))
    # Derive a user-facing structure label without changing existing structure values
    structure_label = structure
    try:
        if type_ == "vertical" and len(legs_df) == 2 and {
            "right",
            "strike",
            "qty",
        } <= set(legs_df.columns):
            right = str(legs_df["right"].iloc[0])
            # Identify long vs short strikes
            s0, s1 = float(legs_df["strike"].iloc[0]), float(legs_df["strike"].iloc[1])
            q0, q1 = float(legs_df["qty"].iloc[0]), float(legs_df["qty"].iloc[1])
            # Long strike is attached to the positive-qty leg
            long_k = s0 if q0 > 0 else s1
            short_k = s0 if q0 < 0 else s1
            if right == "C":
                structure_label = "bull call" if long_k < short_k else "bear call"
            elif right == "P":
                structure_label = "bull put" if long_k < short_k else "bear put"
    except Exception:
        pass

    return dict(
        combo_id=combo_id,
        structure=structure,
        structure_label=structure_label,
        underlying=legs_df["underlying"].iloc[0],
        expiry=legs_df["expiry"].iloc[0],
        qty=legs_df["qty"].sum(),
        delta=legs_df["delta"].sum(),
        gamma=legs_df["gamma"].sum(),
        vega=legs_df["vega"].sum(),
        theta=legs_df["theta"].sum(),
        type=type_,
        width=width,
        credit_debit=credit_debit,
        parent_combo_id=None,
        closed_date=None,
        legs=list(legs_df.index),
    )


def _calc_width(legs_df: pd.DataFrame) -> float | None:
    strikes = sorted(set(legs_df["strike"]))
    if len(strikes) <= 1:
        return 0.0
    diffs = [b - a for a, b in zip(strikes[:-1], strikes[1:])]
    return min(diffs) if diffs else 0.0


def _match_calendar(df: pd.DataFrame, used: set[int]) -> List[Dict]:
    combos: List[Dict] = []
    sub = df[~df.index.isin(used)]
    for (strike, right), grp in sub.groupby(["strike", "right"]):
        if len(grp) == 2 and grp["expiry"].nunique() == 2:
            q0, q1 = grp["qty"].iloc[0], grp["qty"].iloc[1]
            if q0 == -q1:
                conids = list(grp.index)
                used.update(conids)
                combos.append(_row("Calendar", df.loc[conids], "calendar", 0.0))
    return combos


def _match_condor(df: pd.DataFrame, used: set[int]) -> List[Dict]:
    combos: List[Dict] = []
    sub = df[~df.index.isin(used)]
    for exp, grp in sub.groupby("expiry"):
        calls = grp[grp["right"] == "C"]
        puts = grp[grp["right"] == "P"]
        if len(calls) == 2 and len(puts) == 2:
            if {1, -1} <= set(calls["qty"]) and {1, -1} <= set(puts["qty"]):
                # Determine orientation of each vertical
                def _orient(g: pd.DataFrame, right_val: str) -> str:
                    # identify long vs short strike
                    # for calls: debit if long lower < short higher; credit otherwise
                    # for puts: debit if long higher > short lower; credit otherwise
                    g2 = g.sort_values("strike")
                    # map by side
                    try:
                        long_k = float(g2[g2["qty"] > 0]["strike"].iloc[0])
                        short_k = float(g2[g2["qty"] < 0]["strike"].iloc[0])
                    except Exception:
                        return "unknown"
                    if right_val == "C":
                        return "debit" if long_k < short_k else "credit"
                    else:
                        return "debit" if long_k > short_k else "credit"
                o_calls = _orient(calls, "C")
                o_puts = _orient(puts, "P")
                if o_calls != "unknown" and o_puts != "unknown" and o_calls == o_puts:
                    conids = list(calls.index) + list(puts.index)
                    used.update(conids)
                    width = _calc_width(df.loc[conids])
                    combos.append(_row("Condor", df.loc[conids], "condor", width))
    return combos


def _match_butterfly(df: pd.DataFrame, used: set[int]) -> List[Dict]:
    combos: List[Dict] = []
    sub = df[~df.index.isin(used)]
    for (exp, right), grp in sub.groupby(["expiry", "right"]):
        if len(grp) == 3:
            qtys = list(grp["qty"])
            if (qtys.count(-2) == 1 and qtys.count(1) == 2) or (
                qtys.count(2) == 1 and qtys.count(-1) == 2
            ):
                conids = list(grp.index)
                used.update(conids)
                width = _calc_width(df.loc[conids])
                combos.append(_row("Butterfly", df.loc[conids], "butterfly", width))
    return combos


def _pair_same_strike(df: pd.DataFrame, used: set[int]) -> List[List[int]]:
    mask = ~df.index.isin(used)
    sub = df[mask]
    pairs: List[List[int]] = []
    for (u, strk, exp), grp in sub.groupby(["underlying", "strike", "expiry"]):
        if {"C", "P"} <= set(grp["right"]) and grp["qty"].nunique() == 1:
            pairs.append(list(grp.index))
    return pairs


def _sync_with_db(combo_df: pd.DataFrame, pos_df: pd.DataFrame) -> None:
    conn = _db()
    now = _dt.datetime.utcnow().isoformat(timespec="seconds")
    today = _dt.date.today().isoformat()

    active = set(combo_df.index)
    cur = conn.execute(
        "SELECT combo_id, underlying, expiry, structure FROM combos WHERE ts_closed IS NULL"
    )
    open_combos = {}
    for cid, underlying, expiry, structure in cur.fetchall():
        legs = conn.execute(
            "SELECT strike, right FROM legs WHERE combo_id=?", (cid,)
        ).fetchall()
        open_combos[cid] = {
            "underlying": underlying,
            "expiry": expiry,
            "structure": structure,
            "legs": sorted(legs),
        }

    parent_map: Dict[str, str] = {}
    for cid, row in combo_df.iterrows():
        key = sorted([(pos_df.loc[l].strike, pos_df.loc[l].right) for l in row.legs])
        for ocid, data in open_combos.items():
            if (
                data["underlying"] == row.underlying
                and data["structure"] == row.structure
                and data["legs"] == key
                and data["expiry"] != row.expiry
            ):
                parent_map[cid] = ocid
                break

    rolled_parents = set(parent_map.values())

    cur = conn.execute("SELECT combo_id, ts_closed FROM combos")
    for cid, ts_closed in cur.fetchall():
        if cid not in active and ts_closed is None:
            closed_date = today if cid in rolled_parents else None
            conn.execute(
                "UPDATE combos SET ts_closed=?, closed_date=? WHERE combo_id=?",
                (now, closed_date, cid),
            )

    for cid, row in combo_df.iterrows():
        conn.execute(
            "INSERT OR IGNORE INTO combos (combo_id, ts_created, ts_closed, structure, underlying, expiry, type, width, credit_debit, parent_combo_id, closed_date) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                cid,
                now,
                None,
                row.structure,
                row.underlying,
                row.expiry,
                row.get("type"),
                row.get("width"),
                row.get("credit_debit"),
                parent_map.get(cid),
                None,
            ),
        )
        for conid in row.legs:
            leg = pos_df.loc[conid]
            conn.execute(
                "INSERT OR IGNORE INTO legs (combo_id, conid, strike, right) VALUES (?,?,?,?)",
                (cid, int(conid), leg.strike, leg.right),
            )

    conn.commit()
    for cid, parent in parent_map.items():
        combo_df.loc[cid, "parent_combo_id"] = parent


def fetch_persisted_mapping() -> Dict[int, str]:
    """Return mapping of ``conid`` to ``combo_id`` from the SQLite store."""

    conn = _db()
    return {cid: cmb for cid, cmb in conn.execute("SELECT conid, combo_id FROM legs")}
