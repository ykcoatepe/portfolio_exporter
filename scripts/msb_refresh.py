"""CLI to refresh MSB vendor inputs (IBKR/YF + optional FRED HY)."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from psd.datasources.msb_vendor import refresh_vendor_data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh MSB vendor data.")
    parser.add_argument(
        "--vendor-dir",
        type=Path,
        default=Path("data") / "vendor",
        help="Directory containing MSB vendor CSVs",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit status as JSON",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    status = refresh_vendor_data(args.vendor_dir, env=os.environ)
    if args.json:
        print(json.dumps(status, sort_keys=True))
    else:
        parts = [f"{k}={v}" for k, v in sorted(status.items())]
        print("msb_refresh: " + (", ".join(parts) if parts else "no status"))


if __name__ == "__main__":
    main()
