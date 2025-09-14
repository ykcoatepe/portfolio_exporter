"""Memo writer (JSONL, v0.1)."""

from __future__ import annotations

import json
import os
from typing import Any, Dict


def write_jsonl(path: str, obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    line = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
