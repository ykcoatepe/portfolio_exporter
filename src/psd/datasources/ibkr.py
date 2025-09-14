"""IBKR datasource wrappers (v0.1).

These are thin adapters intended to reuse in-repo exporter functions, while
remaining safe under unit tests (no network I/O). Tests can monkeypatch these
functions to supply fixtures.
"""

from __future__ import annotations

from typing import Any, Dict, List


def get_positions(cfg: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    """Return a minimal list of position dicts.

    Expected keys per item: symbol, kind, qty, mark, beta?, legs?
    In production, this can delegate to portfolio_greeks internals. By default
    returns an empty list to keep tests hermetic.
    """
    # TODO: wire to portfolio_exporter.scripts.portfolio_greeks._load_positions (optional)
    return []


def get_margin_status(cfg: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Return margin usage snapshot.

    Keys: used_pct (0..1), available, maintenance, equity.
    Default returns an empty structure; tests will patch.
    """
    return {"used_pct": None, "available": None, "maintenance": None, "equity": None}
