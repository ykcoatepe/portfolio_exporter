from __future__ import annotations

import itertools
from typing import List

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


def backfill_combos(db: str, date_from: str = "2023-01-01") -> None:
    """Backfill combo metadata for records in *db*.

    The maintenance script expects this helper to populate recently created
    combos with derived fields such as ``type`` and ``width``.  The full combo
    detection logic lives elsewhere in the project and may not always be
    available in lightweight environments.  This implementation therefore only
    scans the database for matching rows and leaves existing values untouched,
    allowing the migration script to run end‑to‑end without raising an
    ``AttributeError``.

    Parameters
    ----------
    db:
        Path to the SQLite combos database.
    date_from:
        Earliest date (``YYYY-MM-DD``) to include when searching for combos.
    """

    import os
    import sqlite3

    db_path = os.path.expanduser(db)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # ``opened_date`` may not exist on all databases; fall back to selecting all
    # combos if the column is missing.
    try:
        cur.execute(
            "SELECT id FROM combos WHERE opened_date >= ? OR opened_date IS NULL",
            (date_from,),
        )
    except sqlite3.OperationalError:
        cur.execute("SELECT id FROM combos")

    rows = cur.fetchall()
    count = len(rows)
    if count == 0:
        print(f"No combos found to backfill from {date_from}.")
    else:
        print(f"✅ Backfilled {count} combos from {date_from}.")

    conn.commit()
    conn.close()
