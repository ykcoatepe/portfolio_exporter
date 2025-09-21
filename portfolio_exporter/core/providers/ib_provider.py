from __future__ import annotations

from typing import Any


def _ensure_online(cfg: dict[str, Any]) -> None:
    if cfg.get("data", {}).get("offline"):
        raise RuntimeError("IB provider disabled in offline mode")


def get_quote(symbol: str, cfg: dict[str, Any]) -> dict[str, Any]:
    """Return minimal quote dict. Real implementation can use ib_insync in prod.
    In offline/CI, tests monkeypatch this.
    """
    _ensure_online(cfg)
    # Placeholder real impl could go here; return empty to force fallback in tests
    return {}


def get_intraday_bars(
    symbol: str, cfg: dict[str, Any], minutes: int = 60, prepost: bool = True
) -> list[dict[str, Any]]:
    """Return list of minute bars: {ts, open, high, low, close, volume}.
    Tests will monkeypatch. Default returns [].
    """
    _ensure_online(cfg)
    return []


def get_option_chain(symbol: str, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Return consolidated option chain rows.
    Expected keys: expiry, right, strike, bid, ask, mid, delta, oi, volume
    """
    _ensure_online(cfg)
    return []


def get_shortable(symbol: str, cfg: dict[str, Any]) -> dict[str, Any]:
    _ensure_online(cfg)
    return {"available": None, "fee_rate": None}
