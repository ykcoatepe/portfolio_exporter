"""
migrate_and_backfill.py — Ensure combo DB schema is current and backfill metadata.

Usage:
    python -m portfolio_exporter.scripts.migrate_and_backfill --db /path/to/combos.db --from 2023-01-01

To inspect the last few combos after running, you can execute:

    sqlite3 ~/combos.db "SELECT id, underlying, type, width, credit_debit, parent_combo_id, closed_date FROM combos ORDER BY id DESC LIMIT 10;"
"""

import argparse
import os
import sqlite3

from portfolio_exporter.core import chain
from portfolio_exporter.core.io import migrate_combo_schema


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Migrate combo DB schema and backfill metadata"
    )
    ap.add_argument(
        "--db",
        default=os.getenv(
            "PE_DB_PATH", os.path.expanduser("~/iCloudDrive/Downloads/combos.db")
        ),
        help="Path to combo SQLite database",
    )
    ap.add_argument(
        "--from",
        dest="date_from",
        default="2023-01-01",
        help="Earliest date to backfill from (YYYY-MM-DD)",
    )
    args = ap.parse_args()

    db_path = os.path.expanduser(args.db)
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")

    print(f"📂 Using DB: {db_path}")
    conn = sqlite3.connect(db_path)
    migrate_combo_schema(conn)
    conn.close()
    print("✅ Schema migration complete.")

    chain.backfill_combos(db=db_path, date_from=args.date_from)
    print(f"✅ Backfill complete from {args.date_from}.")


if __name__ == "__main__":
    main()
