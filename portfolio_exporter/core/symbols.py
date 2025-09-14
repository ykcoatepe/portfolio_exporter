from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Iterable, List

# Default search locations relative to repository root / working directory
_DEFAULT_MAPS: List[str] = ["config/symbol_aliases.json", ".config/symbol_aliases.json"]


def load_alias_map(extra: Iterable[str] = ()) -> Dict[str, str]:
    """Load symbol alias mappings from JSON files and optional env.

    Precedence (last wins):
    - Paths provided in `extra` (in order)
    - Defaults: config/symbol_aliases.json, .config/symbol_aliases.json
    - Environment variable MOMO_ALIASES_JSON (inline JSON)

    Returns a dict with UPPERCASE keys and values.
    """
    paths = list(extra) + _DEFAULT_MAPS
    out: Dict[str, str] = {}
    for p in paths:
        if not p:
            continue
        pp = Path(p).expanduser()
        if pp.exists():
            try:
                data = json.loads(pp.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    out.update({str(k): str(v) for k, v in data.items()})
            except Exception:
                # Ignore malformed files; caller can validate separately if needed
                pass
    # Support ENV inline JSON as last resort
    env = os.getenv("MOMO_ALIASES_JSON")
    if env:
        try:
            data = json.loads(env)
            if isinstance(data, dict):
                out.update({str(k): str(v) for k, v in data.items()})
        except Exception:
            pass
    return {k.upper(): v.upper() for k, v in out.items()}


def normalize_symbols(raw: Iterable[str], alias_map: Dict[str, str]) -> List[str]:
    """Normalize and alias a sequence of raw symbol strings.

    - Strips whitespace and uppercases symbols
    - Applies alias mapping where available
    - Filters out empty results
    """
    out: List[str] = []
    for s in raw:
        sym = str(s).strip().upper()
        if not sym:
            continue
        sym = alias_map.get(sym, sym)
        if sym:
            out.append(sym)
    return out

