from __future__ import annotations

from typing import Any, Dict, List
from datetime import datetime
import os
import json
import time
import math


def _ensure_online(cfg: Dict[str, Any]) -> None:
    if cfg.get("data", {}).get("offline"):
        raise RuntimeError("Yahoo provider disabled in offline mode")


def _cache_cfg(cfg: Dict[str, Any]) -> tuple[bool, str, int]:
    d = cfg.get("data", {}).get("cache", {}) if isinstance(cfg.get("data", {}), dict) else {}
    enabled = bool(d.get("enabled", False))
    cdir = str(d.get("dir", "out/.cache"))
    ttl = int(d.get("ttl_sec", 60))
    return enabled, cdir, ttl


def _cache_read(cfg: Dict[str, Any], key: str) -> Any | None:
    enabled, cdir, ttl = _cache_cfg(cfg)
    if not enabled:
        return None
    path = os.path.join(cdir, f"yahoo_{key}.json")
    try:
        if not os.path.exists(path):
            return None
        age = time.time() - os.path.getmtime(path)
        if ttl and age > ttl:
            return None
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _cache_write(cfg: Dict[str, Any], key: str, obj: Any) -> None:
    enabled, cdir, _ = _cache_cfg(cfg)
    if not enabled:
        return
    try:
        os.makedirs(cdir, exist_ok=True)
        path = os.path.join(cdir, f"yahoo_{key}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh)
    except Exception:
        pass


def get_summary(symbol: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Return float/short/avg vols and premarket if available.
    Real impl may use yfinance.Ticker; tests will monkeypatch.
    """
    # Try cache first (works even in offline mode)
    ck = f"summary_{symbol.upper()}"
    cached = _cache_read(cfg, ck)
    if isinstance(cached, dict) and cached:
        return cached
    _ensure_online(cfg)
    try:
        import yfinance as yf  # type: ignore

        t = yf.Ticker(symbol)
        info = t.fast_info if hasattr(t, "fast_info") else {}
        pre_price = getattr(t, "prepost", None)
        # Best effort
        out = {
            "float_shares": getattr(info, "shares_float", None) or info.get("shares_float"),
            "short_percent_float": info.get("short_percent_of_float"),
            "avg_vol_10d": info.get("ten_day_average_volume"),
            "avg_vol_3m": info.get("three_month_average_volume"),
            "pre_market_price": getattr(t, "pre_market_price", None) or (pre_price if isinstance(pre_price, (int, float)) else None),
            "last": info.get("last_price") or info.get("last_trade_price") or None,
            "prev_close": info.get("previous_close") or None,
        }
        _cache_write(cfg, ck, out)
        return out
    except Exception:
        return {}


def get_intraday_bars(symbol: str, cfg: Dict[str, Any], minutes: int = 60, prepost: bool = True) -> List[Dict[str, Any]]:
    # Try cache first
    ck = f"bars_{symbol.upper()}_{minutes}_{1 if prepost else 0}"
    cached = _cache_read(cfg, ck)
    if isinstance(cached, list) and cached:
        return cached
    try:
        _ensure_online(cfg)
        import yfinance as yf  # type: ignore

        # Fetch up to last `minutes` 1m bars. Using period='90m' to be safe.
        period = "90m" if minutes <= 90 else "1d"
        df = yf.download(tickers=symbol, period=period, interval="1m", prepost=prepost, progress=False)
        if df is None or len(df) == 0:
            return []
        # Normalize columns to lower-case keys and output list of dicts
        rows: List[Dict[str, Any]] = []
        # yfinance returns chronological ascending; take the last `minutes` rows
        tail = df.tail(minutes)
        for idx, r in tail.iterrows():
            try:
                rows.append(
                    {
                        "ts": int(idx.timestamp()) if hasattr(idx, "timestamp") else None,
                        "open": float(r.get("Open", r.get("open", math.nan))),
                        "high": float(r.get("High", r.get("high", math.nan))),
                        "low": float(r.get("Low", r.get("low", math.nan))),
                        "close": float(r.get("Close", r.get("close", math.nan))),
                        "volume": int(r.get("Volume", r.get("volume", 0)) or 0),
                    }
                )
            except Exception:
                continue
        rows = [b for b in rows if not any(v is None or (isinstance(v, float) and math.isnan(v)) for v in (b["open"], b["high"], b["low"], b["close"]))]
        _cache_write(cfg, ck, rows)
        return rows
    except Exception:
        return []


def get_option_chain(symbol: str, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    # Try cache first
    ck = f"chain_{symbol.upper()}"
    cached = _cache_read(cfg, ck)
    if isinstance(cached, list) and cached:
        return cached
    try:
        _ensure_online(cfg)
        import yfinance as yf  # type: ignore

        t = yf.Ticker(symbol)
        expiries = list(getattr(t, "options", []) or [])
        if not expiries:
            return []
        # Pick nearest expiry
        expiry_iso = expiries[0]
        # yfinance uses YYYY-MM-DD; convert to YYYYMMDD
        try:
            exp_yymmdd = datetime.strptime(expiry_iso, "%Y-%m-%d").strftime("%Y%m%d")
        except Exception:
            exp_yymmdd = expiry_iso.replace("-", "")
        oc = t.option_chain(expiry_iso)
        rows: List[Dict[str, Any]] = []
        for side, df in (("C", getattr(oc, "calls", None)), ("P", getattr(oc, "puts", None))):
            if df is None or len(df) == 0:
                continue
            for _, r in df.iterrows():
                try:
                    rows.append(
                        {
                            "symbol": symbol.upper(),
                            "expiry": exp_yymmdd,
                            "right": side,
                            "strike": float(r.get("strike", 0.0)),
                            "bid": float(r.get("bid", 0.0)),
                            "ask": float(r.get("ask", 0.0)),
                            "last": float(r.get("lastPrice", r.get("last_price", 0.0))),
                            "volume": int(r.get("volume", 0) or 0),
                            "oi": int(r.get("openInterest", r.get("open_interest", 0)) or 0),
                        }
                    )
                except Exception:
                    continue
        _cache_write(cfg, ck, rows)
        return rows
    except Exception:
        return []
