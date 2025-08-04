from __future__ import annotations

import datetime as _dt
import hashlib
import logging
import pathlib
import sqlite3
from typing import Dict, List

import pandas as pd

log = logging.getLogger(__name__)

# ── database setup ────────────────────────────────────────────────────────────
DB_PATH = pathlib.Path.home() / ".portfolio_exporter" / "combos.db"
DB_PATH.parent.mkdir(exist_ok=True)

_DDL = """
CREATE TABLE IF NOT EXISTS combos (
    combo_id TEXT PRIMARY KEY,
    ts_created TEXT,
    ts_closed TEXT,
    structure TEXT,
    underlying TEXT,
    expiry TEXT
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
    return conn


# ---------- util helpers --------------------------------------------------
def _hash_combo(conids: List[int]) -> str:
    h = hashlib.sha256()
    for cid in sorted(conids):
        h.update(str(cid).encode())
    return h.hexdigest()[:16]


# ---------- public API ----------------------------------------------------
def detect_combos(pos_df: pd.DataFrame) -> pd.DataFrame:
    """Group legs into combos and persist mapping.

    ``pos_df`` must be indexed by ``conId`` and include the following columns:
    ``underlying``, ``qty``, ``right``, ``strike``, ``expiry``,
    ``delta``, ``gamma``, ``vega`` and ``theta``.

    Returns a DataFrame with one row per combo summarising the greeks and
    including the list of legs.
    """

    # guarantee the column is present (stock legs will have <NA>)
    if "right" not in pos_df.columns:
        pos_df["right"] = pd.NA

    combos: List[Dict] = []
    used: set[int] = set()

    # 1) try to match verticals
    for idx, leg in pos_df.iterrows():
        if idx in used or leg["right"] not in {"C", "P"}:
            continue
        opp = pos_df[
            (pos_df["underlying"] == leg["underlying"])
            & (pos_df["expiry"] == leg["expiry"])
            & (pos_df["right"] == leg["right"])
            & (pos_df["qty"] == -leg["qty"])
        ]
        opp = opp[opp.index != idx]  # exclude itself
        if len(opp) == 1:
            other = opp.iloc[0]
            legs_idx = [idx, other.name]
            used.update(legs_idx)
            combos.append(
                _row(
                    "VertCall" if leg["right"] == "C" else "VertPut",
                    pos_df.loc[legs_idx],
                )
            )
            continue

    # 2) single straddles (buy or sell)
    for conids in _pair_same_strike(pos_df, used):
        used.update(conids)
        combos.append(_row("Straddle", pos_df.loc[conids]))

    # 3) group leftover singles
    for idx in pos_df.index.difference(used):
        combos.append(_row("Single", pos_df.loc[[idx]]))

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
                "legs",
            ]
        ).set_index("combo_id")
    else:
        combo_df = combo_df.set_index("combo_id")
    _sync_with_db(combo_df, pos_df)
    return combo_df


# ---------- helpers -------------------------------------------------------
def _row(structure: str, legs_df: pd.DataFrame) -> Dict:
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
        legs=list(legs_df.index),
    )


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

    # mark inactive combo_ids as closed
    active = set(combo_df.index)
    cur = conn.execute("SELECT combo_id, ts_closed FROM combos")
    for cid, ts_closed in cur.fetchall():
        if cid not in active and ts_closed is None:
            conn.execute("UPDATE combos SET ts_closed=? WHERE combo_id=?", (now, cid))

    # upsert active combos and legs
    for cid, row in combo_df.iterrows():
        conn.execute(
            "INSERT OR IGNORE INTO combos VALUES (?,?,?,?,?,?)",
            (cid, now, None, row.structure, row.underlying, row.expiry),
        )
        for conid in row.legs:
            leg = pos_df.loc[conid]
            conn.execute(
                "INSERT OR IGNORE INTO legs VALUES (?,?,?,?)",
                (cid, int(conid), leg.strike, leg.right),
            )

    conn.commit()


def fetch_persisted_mapping() -> Dict[int, str]:
    """Return mapping of ``conid`` to ``combo_id`` from the SQLite store."""

    conn = _db()
    return {cid: cmb for cid, cmb in conn.execute("SELECT conid, combo_id FROM legs")}
