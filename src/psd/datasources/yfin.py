"""Yahoo Finance helpers for PSD (v0.1)."""

from __future__ import annotations

import math
from typing import Any

try:
    from portfolio_exporter.core.providers import yahoo_provider
except Exception:  # pragma: no cover - fallback in minimal envs
    yahoo_provider = None  # type: ignore


_VIX_LAST: float | None = None


def get_vix(cfg: dict[str, Any] | None = None) -> float | None:
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


def get_closes(symbol: str, days: int = 60, cfg: dict[str, Any] | None = None) -> list[float]:
    """Return recent close prices for VaR calculation.

    Uses yfinance via provider or returns [] when unavailable. Tests can
    monkeypatch this to return a synthetic series.
    """
    try:
        import yfinance as yf  # type: ignore

        period = f"{max(days, 30)}d"
        df = yf.download(tickers=symbol, period=period, interval="1d", progress=False, auto_adjust=False)
        if df is None or len(df) == 0:
            return []
        closes = df.get("Close") or df.get("close")
        if closes is None:
            return []
        return [float(x) for x in list(closes.tail(days).values)]
    except Exception:
        return []


def get_earnings_date(symbol: str, cfg: dict[str, Any] | None = None) -> str | None:
    """Optional earnings date helper. Returns YYYY-MM-DD or None.

    Minimal placeholder to avoid coupling. Tests can patch.
    """
    return None


def fill_equity_marks_from_yf(symbols: list[str]) -> dict[str, float | None]:
    """Best-effort Yahoo Finance fallback for missing equity marks.

    Returns a mapping of ``symbol`` → ``mark`` where ``mark`` is ``None`` when
    a lookup fails. This helper never raises so that callers can treat it as a
    soft enrichment step.
    """
    unique = sorted({sym.strip().upper() for sym in symbols if sym})
    if not unique:
        return {}
    try:
        import yfinance as yf  # type: ignore
    except Exception:
        return {sym: None for sym in unique}

    out: dict[str, float | None] = {sym: None for sym in unique}
    for sym in unique:
        price: float | None = None
        try:
            ticker = yf.Ticker(sym)
            fast = getattr(ticker, "fast_info", {}) or {}
            for key in (
                "last_price",
                "last_trade_price",
                "regular_market_price",
                "previous_close",
                "last_close",
            ):
                val = fast.get(key)
                if val is None:
                    continue
                try:
                    price = float(val)
                except Exception:
                    price = None
                else:
                    if math.isnan(price):
                        price = None
                if price is not None:
                    break
            if price is None:
                hist = ticker.history(period="1d")
                if getattr(hist, "empty", True):
                    price = None
                else:
                    try:
                        close_val = hist["Close"].iloc[-1]
                        price = float(close_val)
                    except Exception:
                        price = None
            if price is not None and price < 0:
                price = None
        except Exception:
            price = None
        out[sym] = price
    return out
