"""PSD CLI table rendering (v0.1)."""

from __future__ import annotations

from typing import Any, Dict, List


def render_table(rows: List[Dict[str, Any]]) -> str:
    """Return a simple text table for alerts.

    Keeps tests independent of rich. Columns: uid, sleeve, kind, R, stop, target, mark, alert
    """
    cols = ["uid", "sleeve", "kind", "R", "stop", "target", "mark", "alert"]
    header = " | ".join(cols)
    lines = [header, "-" * len(header)]
    for r in rows:
        lines.append(
            " | ".join(str(r.get(c, "")) for c in cols)
        )
    return "\n".join(lines)
