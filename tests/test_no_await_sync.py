from __future__ import annotations

import pathlib
import re

SKIP_PARTS = {
    ".git",
    "__pycache__",
    "build",
    "dist",
    "docs",
    "node_modules",
    "tests",
    ".venv",
    ".venv_codex",
    "venv",
}

PATTERN = re.compile(r"await\s+\w+_sync\s*\(")


def test_no_await_sync_facade() -> None:
    offenders: list[str] = []
    for path in pathlib.Path(".").rglob("*.py"):
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if PATTERN.search(text):
            offenders.append(str(path))
    assert not offenders, "await used on sync facade:\n" + "\n".join(offenders)
