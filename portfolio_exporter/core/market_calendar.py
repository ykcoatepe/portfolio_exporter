from __future__ import annotations

import json
import os
from datetime import datetime, time
from typing import Optional, Set
from zoneinfo import ZoneInfo

TZ_NY = ZoneInfo("America/New_York")


def _ny_today() -> datetime:
    return datetime.now(TZ_NY)


def load_early_close_set(path: Optional[str]) -> Set[str]:
    """
    Load a JSON list of YYYY-MM-DD (ET/NY date) that are 1:00pm ET early-close days.
    Returns empty set if path missing. Example file:
      ["2025-07-03", "2025-11-28", "2025-12-24"]
    """
    if not path or not os.path.exists(path):
        return set()
    try:
        arr = json.loads(open(path, encoding="utf-8").read())
        return set(arr if isinstance(arr, list) else [])
    except Exception:
        return set()


def infer_close_et(
    default_close: time = time(16, 0),
    early_close_time: time = time(13, 0),
    dates_json: Optional[str] = None,
) -> time:
    """
    Returns the ET close time for TODAY IN NY.
    Precedence:
     1) MOMO_SEN_EARLY_CLOSE_TODAY=1 => early_close_time
     2) If today's NY date in dates_json list => early_close_time
     3) else default_close
    """
    if str(os.getenv("MOMO_SEN_EARLY_CLOSE_TODAY", "")).lower() in ("1", "true", "yes"):
        return early_close_time
    ec = load_early_close_set(dates_json)
    ymd = _ny_today().date().isoformat()
    return early_close_time if ymd in ec else default_close

