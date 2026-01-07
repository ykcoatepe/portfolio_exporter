# SPDX-License-Identifier: MIT
from __future__ import annotations

import re
from pathlib import Path

_ZERO_ASSIGN_PATTERN = re.compile(r"avg_cost\s*[:=](?!=)\s*0(?:\.0+)?\b")


def test_no_avg_cost_zero_assignments() -> None:
    project_root = Path(__file__).resolve().parents[4]
    target_dir = project_root / "libs" / "py" / "positions_engine"
    offending: list[Path] = []
    for path in target_dir.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if _ZERO_ASSIGN_PATTERN.search(text):
            offending.append(path.relative_to(project_root))
    assert not offending, (
        f"Found avg_cost zero assignments in: {', '.join(str(p) for p in offending)}"
    )
