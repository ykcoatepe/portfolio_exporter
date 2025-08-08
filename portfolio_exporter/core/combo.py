from __future__ import annotations

import datetime as _dt
import hashlib
import logging
import os
import pathlib
import sqlite3
from typing import Dict, List

from .io import migrate_combo_schema
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

    # Under pytest, prefer a repo-local temporary path to avoid sandbox issues
    if os.environ.get("PYTEST_CURRENT_TEST"):
        local_p = pathlib.Path.cwd() / "tmp_test_run" / "combos.db"
        local_p.parent.mkdir(parents=True, exist_ok=True)
        return local_p

    # Preferred location alongside other app outputs
    try:
        outdir = pathlib.Path(getattr(settings, "output_dir", ".")).expanduser()
    except Exception:
        outdir = pathlib.Path.cwd()
    home_p = outdir / "combos.db"
    try:
        home_p.parent.mkdir(parents=True, exist_ok=True)
        # Probe writability by opening a temporary connection in WAL mode
        # without creating the file permanently (best-effort).
        with sqlite3.connect(home_p) as _:
            pass
        return home_p
    except Exception:
        # Fall back to a repo-local path to avoid sandbox restrictions
        local_p = pathlib.Path.cwd() / "tmp_test_run" / "combos.db"
        local_p.parent.mkdir(parents=True, exist_ok=True)
        return local_p


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
    conn = sqlite3.connect(DB_PATH)
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


# ---------- helpers -------------------------------------------------------
def _row(
    structure: str,
    legs_df: pd.DataFrame,
    type_: str,
    width: float | None = None,
    credit_debit: float | None = None,
) -> Dict:
    combo_id = _hash_combo(list(legs_df.index))
    return dict(
        combo_id=combo_id,
        structure=structure,
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
                "INSERT OR IGNORE INTO legs VALUES (?,?,?,?)",
                (cid, int(conid), leg.strike, leg.right),
            )

    conn.commit()
    for cid, parent in parent_map.items():
        combo_df.loc[cid, "parent_combo_id"] = parent


def fetch_persisted_mapping() -> Dict[int, str]:
    """Return mapping of ``conid`` to ``combo_id`` from the SQLite store."""

    conn = _db()
    return {cid: cmb for cid, cmb in conn.execute("SELECT conid, combo_id FROM legs")}
