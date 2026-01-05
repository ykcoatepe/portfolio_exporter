#!/usr/bin/env python3
"""Guard that ensures live defaults use IBKR Gateway port 4001.

Flags legacy TWS port defaults (7496/7497) unless context mentions
"fallback", "paper", "simulated", or "example".
"""

from __future__ import annotations

import pathlib
import re
import sys
from collections.abc import Iterable

ALLOW_IF = re.compile(r"(paper|simulated|example|fallback|legacy)", re.IGNORECASE)
CODE_PATTERNS: tuple[tuple[str, str], ...] = (
    # Legacy TWS defaults that should be 4001 (Gateway)
    ("IB_PORT=7496", "should be 4001 (Gateway)"),
    ("IB_PORT=7497", "paper port without context"),
    ('os.getenv("IB_PORT","7496")', "should be 4001"),
    ("os.getenv('IB_PORT','7496')", "should be 4001"),
    ('os.getenv("IB_PORT","7497")', "paper default without context"),
    ("os.getenv('IB_PORT','7497')", "paper default without context"),
    ("os.environ.get('IB_PORT','7496')", "should be 4001"),
    ('os.environ.get("IB_PORT","7496")', "should be 4001"),
    ("os.environ.get('IB_PORT','7497')", "paper default without context"),
    ('os.environ.get("IB_PORT","7497")', "paper default without context"),
)

SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "dist",
    "build",
    "__pycache__",
    "iv_history",
    ".ruff_cache",
    "legacy",
    "run",
    "local_backup",
    ".venv_codex",
    ".venv_pkgtest",
}
SKIP_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".so",
    ".dll",
    ".log",
    ".db",
    ".sqlite",
    ".png",
    ".jpg",
    ".jpeg",
}


def _should_skip(path: pathlib.Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def _iter_files(root: pathlib.Path) -> Iterable[pathlib.Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if _should_skip(path):
            continue
        if path.suffix in SKIP_SUFFIXES:
            continue
        yield path


def main() -> int:
    bad: list[str] = []
    for file_path in _iter_files(pathlib.Path(".")):
        if file_path.name == "check_ib_port_defaults.py":
            continue
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        lines = text.splitlines()
        for idx, line in enumerate(lines):
            context = "\n".join(lines[max(0, idx - 1) : idx + 2])
            for needle, label in CODE_PATTERNS:
                if needle not in line:
                    continue
                if ALLOW_IF.search(context):
                    continue
                bad.append(f"{file_path}:{idx + 1}:{label}: {line.strip()}")
        # Heuristic for config/docs defaults like "Socket port 7497"
        for idx, line in enumerate(lines):
            if "7497" not in line:
                continue
            if ALLOW_IF.search(line):
                continue
            if re.search(r"Socket port.*7497", line, re.IGNORECASE):
                bad.append(f"{file_path}:{idx + 1}:socket-default: {line.strip()}")

    if bad:
        print(
            "Found unintended legacy TWS defaults (should be 4001 for live):",
            file=sys.stderr,
        )
        for item in bad:
            print(f"  {item}", file=sys.stderr)
        return 1

    print("OK: no unintended 7496/7497 defaults found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
