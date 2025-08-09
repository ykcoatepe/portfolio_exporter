"""
migrate_and_backfill.py — Ensure combo DB schema is current and backfill metadata.

Usage examples:
    python -m portfolio_exporter.scripts.migrate_and_backfill --from 2023-01-01
    python -m portfolio_exporter.scripts.migrate_and_backfill --db ~/.portfolio_exporter/combos.db --from 2024-01-01

To inspect the last few combos after running, you can execute:

    sqlite3 ~/combos.db "SELECT id, underlying, type, width, credit_debit, parent_combo_id, closed_date FROM combos ORDER BY id DESC LIMIT 10;"
"""

import argparse
from pathlib import Path
import sys
import sqlite3

from portfolio_exporter.core import chain
from portfolio_exporter.core.io import migrate_combo_schema
from portfolio_exporter.core.chain import get_combo_db_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate schema and backfill combo metadata."
    )
    parser.add_argument(
        "--db",
        default=None,
        help=(
            "Path to combos.db. If omitted, uses PE_DB_PATH or "
            "settings.output_dir/combos.db"
        ),
    )
    parser.add_argument(
        "--from",
        dest="date_from",
        default=None,
        help="Backfill combos opened on/after this date (YYYY-MM-DD). Optional.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    db_path = Path(args.db).expanduser() if args.db else get_combo_db_path()

    if not db_path.exists():
        print(
            f"No combos.db found at: {db_path}\n"
            "Tip: generate one by running the Greeks workflow first, e.g.:\n"
            "  python -m portfolio_exporter.scripts.portfolio_greeks --combo-types all\n"
            "Or set a permanent location with: export PE_DB_PATH=~/.portfolio_exporter/combos.db\n",
            file=sys.stderr,
        )
        sys.exit(2)

    print(f"📂 Using DB: {db_path}")
    conn = sqlite3.connect(str(db_path))
    migrate_combo_schema(conn)
    conn.close()
    print("✅ Schema migration complete.")

    date_from = args.date_from or "2023-01-01"
    chain.backfill_combos(db=str(db_path), date_from=date_from)
    print(f"✅ Backfill complete from {date_from}.")


if __name__ == "__main__":
    main()
