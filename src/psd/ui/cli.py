"""PSD CLI table rendering (v0.1)."""

from __future__ import annotations

from typing import Any, Dict, List


def render_table(rows: List[Dict[str, Any]]) -> str:
    cols = ["uid", "sleeve", "kind", "R", "stop", "target", "mark", "alert"]
    header = " | ".join(cols)
    lines = [header, "-" * len(header)]
    for r in rows:
        lines.append(" | ".join(str(r.get(c, "")) for c in cols))
    return "\n".join(lines)


def render_dashboard(dto: Dict[str, Any]) -> str:
    """Render top banner + table with breach badges.

    dto: { snapshot: {vix, delta_beta, var95_1d, band, breaches, breakers, margin_used?}, rows: [...] }
    """
    snap = dto.get("snapshot", {})
    rows = dto.get("rows", [])
    vix = snap.get("vix", 0.0)
    regime = "<15" if vix < 15 else ("15-25" if vix <= 25 else ">25")
    margin_pct = float(snap.get("margin_used", 0.0)) * 100.0
    top = f"Regime: {regime} | Δβ: {snap.get('delta_beta', 0):.4f} | VaR95(1d): {snap.get('var95_1d', 0):.2f} | Margin%: {margin_pct:.1f}"
    lines = [top]
    breaches = snap.get("breaches", {}) or {}
    breakers = snap.get("breakers", {}) or {}
    active = [k for k, v in {**breaches, **breakers}.items() if v]
    if active:
        lines.append("BREACH: " + ",".join(active))
    lines.append("")
    lines.append(render_table(rows))
    return "\n".join(lines)
