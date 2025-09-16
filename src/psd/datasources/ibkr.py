"""IBKR datasource wrappers (v0.1).

These are thin adapters intended to reuse in-repo exporter functions, while
remaining safe under unit tests (no network I/O). Tests can monkeypatch these
functions to supply fixtures.
"""

from __future__ import annotations

from typing import Any, Dict, List


def get_positions(cfg: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    """Return PSD position dicts, wired to portfolio_greeks when available.

    Behavior
    - Attempts to import and call ``portfolio_exporter.scripts.portfolio_greeks._load_positions``
      to fetch a live snapshot from IBKR (requires TWS/Gateway). On failure, returns ``[]``.
    - Transforms the resulting DataFrame rows into PSD position dicts expected by the engine:
      equity rows as kind="equity" and aggregated option legs per underlying as kind="option".

    Notes
    - Keeps this logic light and tolerant; missing prices default to 0.0 to satisfy
      non-negative ``mark`` constraints on the Position dataclass.
    - Tests monkeypatch this function directly; no network I/O occurs during unit tests.
    """
    # Lazy import so PSD remains usable without portfolio_greeks/network
    try:
        from portfolio_exporter.scripts import portfolio_greeks as pg  # type: ignore
        import pandas as pd  # type: ignore
    except Exception:
        return []

    try:
        df = pg._load_positions()  # pragma: no cover – tests patch this function
        if df is None:
            return []
    except Exception:
        return []

    try:
        import math
        # Normalize expected columns
        cols = set(df.columns)
        for c in [
            "symbol",
            "underlying",
            "secType",
            "qty",
            "price",
            "right",
            "strike",
            "expiry",
        ]:
            if c not in cols:
                # tolerate missing; downstream uses defaults
                df[c] = None

        positions: List[Dict[str, Any]] = []

        # 1) Equities / ETFs
        eq = df[(df["secType"].astype(str).isin(["STK", "ETF"])) & (df["qty"].fillna(0) != 0)]
        if not eq.empty:
            for _, r in eq.iterrows():
                sym = str(r.get("symbol") or r.get("underlying") or "").upper()
                if not sym:
                    continue
                try:
                    qty = int(r.get("qty") or 0)
                except Exception:
                    qty = 0
                try:
                    mark = float(r.get("price"))
                    if math.isnan(mark):
                        mark = 0.0
                except Exception:
                    mark = 0.0
                positions.append(
                    {
                        "uid": f"STK-{sym}",
                        "symbol": sym,
                        "sleeve": "core",
                        "kind": "equity",
                        "qty": qty,
                        "mark": max(0.0, float(mark)),
                    }
                )

        # 2) Options/FOP – aggregate legs per underlying into a Position(kind='option')
        opt = df[(df["secType"].astype(str).isin(["OPT", "FOP"])) & (df["qty"].fillna(0) != 0)]
        if not opt.empty:
            by_under: Dict[str, list[Dict[str, Any]]] = {}
            # Import here to avoid import cycles at module import time
            from ..models import OptionLeg  # type: ignore

            for _, r in opt.iterrows():
                sym = str(r.get("underlying") or r.get("symbol") or "").upper()
                if not sym:
                    continue
                try:
                    strike = float(r.get("strike")) if r.get("strike") is not None else None
                except Exception:
                    strike = None
                try:
                    qty = int(r.get("qty") or 0)
                except Exception:
                    qty = 0
                try:
                    price = float(r.get("price"))
                    if math.isnan(price):
                        price = 0.0
                except Exception:
                    price = 0.0
                exp_raw = r.get("expiry")
                expiry = None
                if isinstance(exp_raw, str):
                    expiry = exp_raw.replace("-", "")[:8]  # normalize YYYYMMDD
                elif pd.notna(exp_raw):
                    expiry = str(exp_raw)
                try:
                    leg_obj = OptionLeg(
                        symbol=sym,
                        expiry=(expiry or ""),
                        right=(str(r.get("right") or "").upper() or "C"),
                        strike=float(strike or 0.0),
                        qty=int(qty),
                        price=float(price),
                        delta=None,
                    )
                    by_under.setdefault(sym, []).append(leg_obj)  # type: ignore[arg-type]
                except Exception:
                    continue

            for sym, legs in by_under.items():
                positions.append(
                    {
                        "uid": f"OPT-{sym}",
                        "symbol": sym,
                        "sleeve": "theta",
                        "kind": "option",
                        "qty": 0,
                        "mark": 0.0,
                        "legs": legs,
                    }
                )

        # Optional lightweight equity mark enrichment (best-effort)
        try:
            import os as _os
            if not _os.getenv("PE_TEST_MODE"):
                # Build a symbol -> price map using Yahoo summary (cached when enabled)
                syms = sorted({p["symbol"] for p in positions if p.get("kind") == "equity"})
                quotes: Dict[str, float] = {}
                provider = None
                try:
                    from portfolio_exporter.core.providers import yahoo_provider as _yp  # type: ignore

                    provider = _yp
                except Exception:
                    provider = None
                for sym in syms:
                    last: float | None = None
                    if provider is not None:
                        try:
                            s = provider.get_summary(sym, cfg or {})
                            v = s.get("last") or s.get("prev_close")
                            last = float(v) if v is not None else None
                        except Exception:
                            last = None
                    if last is None:
                        try:
                            import yfinance as yf  # type: ignore

                            t = yf.Ticker(sym)
                            fi = getattr(t, "fast_info", {})
                            last = fi.get("last_price") or fi.get("last_trade_price") or fi.get("previous_close")
                            last = float(last) if last is not None else None
                        except Exception:
                            last = None
                    if last is not None and last >= 0:
                        quotes[sym] = float(last)
                if quotes:
                    for p in positions:
                        if p.get("kind") == "equity":
                            sym = str(p.get("symbol", "")).upper()
                            if sym in quotes:
                                p["mark"] = float(quotes[sym])
        except Exception:
            # best-effort enrichment only
            pass
        return positions
    except Exception:
        return []


def get_margin_status(cfg: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Return margin usage snapshot.

    Keys: used_pct (0..1), available, maintenance, equity.
    Default returns an empty structure; tests will patch.
    """
    return {"used_pct": None, "available": None, "maintenance": None, "equity": None}
