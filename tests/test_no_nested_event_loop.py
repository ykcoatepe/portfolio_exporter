from __future__ import annotations

import pathlib
import re

BAD_PATTERNS = [
    r"asyncio\.run\(",
    r"run_until_complete\(",
    r"\bib\.run\(",
    r"util\.startLoop\(",
]


ALLOWED = {
    "src/psd/ingestor/main.py",
    "src/psd/web/server.py",
    "src/psd/sentinel/scan.py",
}


def test_no_nested_loop_runners() -> None:
    offenders: list[str] = []
    src_root = pathlib.Path("src")
    for path in src_root.rglob("*.py"):
        rel = str(path)
        if rel in ALLOWED:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(re.search(pattern, text) for pattern in BAD_PATTERNS):
            offenders.append(str(path))
    assert not offenders, "Nested loop runners found:\n" + "\n".join(offenders)
