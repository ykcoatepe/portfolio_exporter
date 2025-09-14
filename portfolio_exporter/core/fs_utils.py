from __future__ import annotations

import glob
import os
import re
from pathlib import Path
from typing import Iterable, Optional, Tuple

_DATE = re.compile(r"(20\d{2})(\d{2})(\d{2})")


def _score_file(p: Path) -> Tuple[int, float]:
    """
    Score: (YYYYMMDD as int if present else 0, mtime).
    Higher is newer. Used to select newest matching file.
    """
    name = p.name
    dt = 0
    m = _DATE.search(name)
    if m:
        try:
            dt = int("".join(m.groups()))
        except Exception:
            dt = 0
    try:
        mt = p.stat().st_mtime
    except Exception:
        mt = 0.0
    return (dt, mt)


def find_latest_file(
    search_dirs: Iterable[str],
    patterns: Iterable[str] = ("meme_scan_*.csv",),
) -> Optional[str]:
    """
    Search dirs in order for files matching patterns.
    Return path to the newest by (date in name, then mtime), else None.
    """
    candidates: list[Path] = []
    for d in search_dirs:
        if not d:
            continue
        base = Path(d).expanduser()
        if not base.exists():
            continue
        for pat in patterns:
            for s in glob.glob(str(base / pat)):
                p = Path(s)
                if p.is_file():
                    candidates.append(p)
    if not candidates:
        return None
    candidates.sort(key=_score_file)
    return str(candidates[-1])


def auto_config(defaults: Iterable[str]) -> Optional[str]:
    """
    Return the first existing config path from the list, else None.
    """
    for p in defaults:
        if not p:
            continue
        q = Path(p).expanduser()
        if q.exists():
            return str(q)
    return None


def auto_chains_dir(candidates: Iterable[str]) -> Optional[str]:
    """
    Return the first existing directory from candidates, else None.
    """
    for c in candidates:
        if not c:
            continue
        q = Path(c).expanduser()
        if q.is_dir():
            return str(q)
    return None


def find_latest_chain_for_symbol(chains_dir: str, symbol: str) -> Optional[str]:
    """
    Pick the latest chain CSV for a symbol under chains_dir.
    Looks for SYMBOL_YYYYMMDD.csv, falls back to SYMBOL.csv.
    """
    base = Path(chains_dir).expanduser()
    if not base.is_dir():
        return None
    sym = symbol.upper()
    files = list(base.glob(f"{sym}_*.csv"))
    if files:
        files.sort(key=_score_file)
        return str(files[-1])
    f = base / f"{sym}.csv"
    return str(f) if f.is_file() else None

