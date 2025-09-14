"""Yahoo Finance helpers for PSD (v0.1)."""

from __future__ import annotations

from typing import Any, Dict, List

try:
    from portfolio_exporter.core.providers import yahoo_provider
except Exception:  # pragma: no cover - fallback in minimal envs
    yahoo_provider = None  # type: ignore


_VIX_LAST: float | None = None


def get_vix(cfg: Dict[str, Any] | None = None) -> float | None:
    """Return latest VIX level using in-repo Yahoo provider when available.

    Returns None if unavailable. Cached per-process for speed.
    """
    try:
        if yahoo_provider is None:
            # no provider; return cached
            return _VIX_LAST
        s = yahoo_provider.get_summary("^VIX", cfg or {})
        v = s.get("last") or s.get("prev_close")
        val = float(v) if v is not None else None
        globals()["_VIX_LAST"] = val
        return val
    except Exception:
        return None


def get_closes(symbol: str, days: int = 60, cfg: Dict[str, Any] | None = None) -> List[float]:
    """Return recent close prices for VaR calculation.

    Uses yfinance via provider or returns [] when unavailable. Tests can
    monkeypatch this to return a synthetic series.
    """
    try:
        import yfinance as yf  # type: ignore

        period = f"{max(days, 30)}d"
        df = yf.download(tickers=symbol, period=period, interval="1d", progress=False)
        if df is None or len(df) == 0:
            return []
        closes = df.get("Close") or df.get("close")
        if closes is None:
            return []
        return [float(x) for x in list(closes.tail(days).values)]
    except Exception:
        return []


def get_earnings_date(symbol: str, cfg: Dict[str, Any] | None = None) -> str | None:
    """Optional earnings date helper. Returns YYYY-MM-DD or None.

    Minimal placeholder to avoid coupling. Tests can patch.
    """
    return None
