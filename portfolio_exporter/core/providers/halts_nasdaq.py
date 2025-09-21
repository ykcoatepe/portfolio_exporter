from __future__ import annotations

import csv
import io
import json
import os
import time
import urllib.request
from typing import Any
from zoneinfo import ZoneInfo


def _cache_path(cfg: dict[str, Any]) -> str:
    data = cfg.get("data", {})
    cache = data.get("cache", {})
    cdir = cache.get("dir") or os.path.join("out", ".cache")
    os.makedirs(cdir, exist_ok=True)
    return os.path.join(cdir, "halts_nasdaq_today.json")


def _cache_ttl(cfg: dict[str, Any]) -> int:
    return int(cfg.get("data", {}).get("cache", {}).get("ttl_sec", 60))


def get_halts_today(cfg: dict[str, Any]) -> dict[str, int]:
    """Return ticker→count map. Offline returns {}.
    Tests will monkeypatch this function; real HTTP can be added later.
    """
    if cfg.get("data", {}).get("offline"):
        return {}

    cpath = _cache_path(cfg)
    ttl = _cache_ttl(cfg)
    try:
        if os.path.exists(cpath) and (time.time() - os.path.getmtime(cpath) <= ttl):
            with open(cpath, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass

    # Placeholder: no real fetch in library by default
    data: dict[str, int] = {}
    try:
        with open(cpath, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass
    return data


# Live halts CSV (times in ET). Tests can monkeypatch these functions.
TZ_NY = ZoneInfo("America/New_York")


def fetch_current_halts_csv(timeout: int = 5) -> list[dict[str, str]]:
    """Fetch Nasdaq Trader Current Trading Halts CSV and return list of dict rows.

    Source: https://www.nasdaqtrader.com/trader.aspx?id=tradehalts
    """
    url = "https://www.nasdaqtrader.com/dynamic/symdir/tradehalts.csv"
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(raw))
    return [dict(row) for row in reader]


def parse_resume_events(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    """Extract resumption events keyed by symbol.

    Returns: {SYM: {halt_time_et, resume_quote_et, resume_trade_et, reason}}
    """
    out: dict[str, dict[str, str]] = {}
    for d in rows:
        sym = (d.get("Issue Symbol") or d.get("Symbol") or "").strip().upper()
        if not sym:
            continue
        rq = (d.get("Resumption Quote Time") or "").strip()
        rt = (d.get("Resumption Trade Time") or "").strip()
        if rq or rt:
            out[sym] = {
                "halt_time_et": (d.get("Halt Time") or "").strip(),
                "resume_quote_et": rq,
                "resume_trade_et": rt,
                "reason": (d.get("Reason Code") or "").strip(),
            }
    return out
