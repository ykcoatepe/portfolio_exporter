"""Memo writer (JSONL, v0.1)."""

from __future__ import annotations

import json
import os
from typing import Any, Dict


def write_jsonl(path: str, obj: Dict[str, Any]) -> None:
    if not path:
        return
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    line = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def write_digest(path: str, kind: str, payload: Dict[str, Any]) -> None:
    obj = {"type": kind, **payload}
    write_jsonl(path, obj)
