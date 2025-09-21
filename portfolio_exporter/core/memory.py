from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _memory_path() -> Path:
    return Path(os.getenv("PE_MEMORY_PATH") or ".codex/memory.json").expanduser()


def _load() -> dict[str, Any]:
    p = _memory_path()
    try:
        if not p.exists():
            return {
                "preferences": {},
                "workflows": {},
                "tasks": [],
                "questions": [],
                "decisions": [],
                "changelog": [],
            }
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"preferences": {}}


def load_memory() -> dict[str, Any]:
    """Public helper to fetch full memory JSON (gracefully empty on errors)."""
    try:
        return _load()
    except Exception:
        return {
            "preferences": {},
            "workflows": {},
            "tasks": [],
            "questions": [],
            "decisions": [],
            "changelog": [],
        }


def _save(data: dict[str, Any]) -> None:
    if os.getenv("MEMORY_READONLY") in ("1", "true", "yes", "True"):  # graceful no-op
        return
    p = _memory_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, sort_keys=True, separators=(",", ":"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


def get_pref(key: str, default: str | None = None) -> str | None:
    """Read a preference under preferences.* using dot notation.

    Example: key="micro_momo.symbols" reads preferences.micro_momo.symbols
    """
    data = _load()
    prefs: Any = data.get("preferences", {})
    if not isinstance(prefs, dict):
        return default
    node: Any = prefs
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node.get(part)
    if node is None:
        return default
    return str(node)


def set_pref(key: str, value: Any) -> None:
    """Set a preference under preferences.* using dot notation and save atomically."""
    data = _load()
    prefs: dict[str, Any] = data.setdefault("preferences", {}) if isinstance(data, dict) else {}
    node: dict[str, Any] = prefs
    parts = key.split(".")
    for part in parts[:-1]:
        nxt = node.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            node[part] = nxt
        node = nxt
    node[parts[-1]] = value
    _save(data)
