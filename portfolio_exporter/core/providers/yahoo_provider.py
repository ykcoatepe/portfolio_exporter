from __future__ import annotations

from typing import Any, Dict, List


def _ensure_online(cfg: Dict[str, Any]) -> None:
    if cfg.get("data", {}).get("offline"):
        raise RuntimeError("Yahoo provider disabled in offline mode")


def get_summary(symbol: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Return float/short/avg vols and premarket if available.
    Real impl may use yfinance.Ticker; tests will monkeypatch.
    """
    _ensure_online(cfg)
    try:
        import yfinance as yf  # type: ignore

        t = yf.Ticker(symbol)
        info = t.fast_info if hasattr(t, "fast_info") else {}
        pre_price = getattr(t, "prepost", None)
        # Best effort
        return {
            "float_shares": getattr(info, "shares_float", None) or info.get("shares_float"),
            "short_percent_float": info.get("short_percent_of_float"),
            "avg_vol_10d": info.get("ten_day_average_volume"),
            "avg_vol_3m": info.get("three_month_average_volume"),
            "pre_market_price": getattr(t, "pre_market_price", None) or (pre_price if isinstance(pre_price, (int, float)) else None),
            "last": info.get("last_price") or info.get("last_trade_price") or None,
            "prev_close": info.get("previous_close") or None,
        }
    except Exception:
        return {}


def get_intraday_bars(symbol: str, cfg: Dict[str, Any], minutes: int = 60, prepost: bool = True) -> List[Dict[str, Any]]:
    _ensure_online(cfg)
    return []


def get_option_chain(symbol: str, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    _ensure_online(cfg)
    return []
