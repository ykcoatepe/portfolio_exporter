from __future__ import annotations

import json
import os
import time
from typing import Any, Dict


def _cache_path(cfg: Dict[str, Any]) -> str:
    data = cfg.get("data", {})
    cache = data.get("cache", {})
    cdir = cache.get("dir") or os.path.join("out", ".cache")
    os.makedirs(cdir, exist_ok=True)
    return os.path.join(cdir, "halts_nasdaq_today.json")


def _cache_ttl(cfg: Dict[str, Any]) -> int:
    return int(cfg.get("data", {}).get("cache", {}).get("ttl_sec", 60))


def get_halts_today(cfg: Dict[str, Any]) -> Dict[str, int]:
    """Return ticker→count map. Offline returns {}.
    Tests will monkeypatch this function; real HTTP can be added later.
    """
    if cfg.get("data", {}).get("offline"):
        return {}

    cpath = _cache_path(cfg)
    ttl = _cache_ttl(cfg)
    try:
        if os.path.exists(cpath) and (time.time() - os.path.getmtime(cpath) <= ttl):
            with open(cpath, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass

    # Placeholder: no real fetch in library by default
    data: Dict[str, int] = {}
    try:
        with open(cpath, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass
    return data

