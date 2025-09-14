"""Run the Portfolio Sentinel Dashboard sentinel (v0.1)."""

from __future__ import annotations

from pprint import pprint
from typing import Any, Dict

from src.psd.sentinel.engine import scan_once


def main() -> None:
    cfg: Dict[str, Any] = {}
    dto = scan_once(cfg)
    rows = dto.get("rows", [])
    print(f"PSD sentinel v0.1: {len(rows)} alerts")
    for r in rows[:10]:
        print(f"- {r['uid']} {r['sleeve']} {r['kind']} R={r['R']} stop={r['stop']} tgt={r['target']} mark={r['mark']} {r['alert']}")


if __name__ == "__main__":
    main()
