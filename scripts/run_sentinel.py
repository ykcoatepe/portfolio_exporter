"""Run the Portfolio Sentinel Dashboard sentinel (v0.1)."""

from __future__ import annotations

import argparse
from typing import Any

from src.psd.sentinel.engine import scan_once
from src.psd.sentinel.sched import run_loop


def main() -> None:
    ap = argparse.ArgumentParser(description="Run Portfolio Sentinel Dashboard")
    ap.add_argument("--loop", action="store_true", help="Run continuous intraday loop")
    ap.add_argument("--interval", type=int, default=60, help="Loop interval in seconds (default: 60)")
    args = ap.parse_args()

    cfg: dict[str, Any] = {}
    if args.loop:
        print(f"Starting sentinel loop at {args.interval}s cadence…")
        run_loop(interval=args.interval, cfg=cfg)
        return

    dto = scan_once(cfg)
    rows = dto.get("rows", [])
    print(f"PSD sentinel v0.1: {len(rows)} alerts")
    for r in rows[:10]:
        print(
            f"- {r['uid']} {r['sleeve']} {r['kind']} R={r['R']} stop={r['stop']} tgt={r['target']} mark={r['mark']} {r['alert']}"
        )


if __name__ == "__main__":
    main()
