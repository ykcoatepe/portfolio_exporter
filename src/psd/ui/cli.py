"""PSD CLI (text) helpers for the Portfolio Sentinel Dashboard.

This module provides lightweight rendering utilities and a small runnable
``run_dash()`` entry that the TUI menu and developer helpers can call.
"""

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
    bstate = snap.get("breaker_state", {}) or {}
    state = bstate.get("state", "ok") if isinstance(bstate, dict) else "ok"
    if state != "ok":
        lines.append(f"BREAKER: {state}")
    active = [k for k, v in {**breaches, **breakers}.items() if v]
    if active:
        lines.append("BREACH: " + ",".join(active))
    lines.append("")
    lines.append(render_table(rows))
    # Footer budgets
    b = dto.get("budgets") or {}
    if isinstance(b, dict):
        th = b.get("theta", {}) or {}
        hd = b.get("hedge", {}) or {}
        def pct(x):
            try: return f"{float(x)*100:.2f}%"
            except Exception: return "0.00%"
        footer = [
            f"θ weekly fees: {pct(th.get('burn',0))}{' WARN' if th.get('warn') else ''}",
            f"Hedge MTD: {pct(hd.get('burn',0))}{' WARN' if hd.get('warn') else ''}",
        ]
        lines.append("")
        lines.extend(footer)
    # Digest message
    if dto.get("digest_path"):
        lines.append(f"Digest saved: {dto['digest_path']}")
    return "\n".join(lines)


def run_dash(cfg: Dict[str, Any] | None = None) -> None:
    """Run a one-shot PSD dashboard render to stdout.

    This uses the same underlying scan used by the CLI scheduler and returns
    a simple text dashboard suitable for terminal output. It intentionally
    avoids heavy imports at module import time for fast startup in the TUI.

    Parameters
    - cfg: optional dictionary to override defaults for the sentinel scan.
    """
    if cfg is None:
        cfg = {}
    # Lazy imports to keep CLI + TUI startup snappy
    from src.psd.sentinel.engine import scan_once  # type: ignore

    dto = scan_once(cfg)
    print(render_dashboard(dto))
