from __future__ import annotations

import csv
import glob
import os
from typing import Dict, Iterable, List, Optional, Tuple, Any

from .micro_momo_types import ChainRow, ScanRow
from .patterns import compute_patterns
from .providers import ib_provider, yahoo_provider, halts_nasdaq


def load_scan_csv(path: str) -> List[ScanRow]:
    rows: List[ScanRow] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            rows.append(ScanRow.from_csv_row(raw))
    return rows


def load_chain_csv(path: str) -> List[ChainRow]:
    rows: List[ChainRow] = []
    # Infer expiry from filename like SYMBOL_YYYYMMDD.csv
    base = os.path.basename(path)
    expiry = ""
    parts = os.path.splitext(base)[0].split("_")
    if len(parts) >= 2 and parts[-1].isdigit():
        expiry = parts[-1]
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            symbol = str(raw.get("symbol", "")).upper()
            right = str(raw.get("right", "")).upper()[:1]
            try:
                row = ChainRow(
                    symbol=symbol,
                    expiry=str(raw.get("expiry", expiry)) or expiry,
                    right=right,
                    strike=float(raw.get("strike", 0.0)),
                    bid=float(raw.get("bid", 0.0)),
                    ask=float(raw.get("ask", 0.0)),
                    last=float(raw.get("last", 0.0)),
                    volume=int(float(raw.get("volume", 0))),
                    oi=int(float(raw.get("oi", 0))),
                )
                rows.append(row)
            except Exception:
                continue
    # Sort by strike then right for stability
    rows.sort(key=lambda r: (r.expiry, r.right, r.strike))
    return rows


def find_chain_file_for_symbol(chains_dir: Optional[str], symbol: str) -> Optional[str]:
    if not chains_dir:
        return None
    pattern = os.path.join(chains_dir, f"{symbol.upper()}_*.csv")
    matches = sorted(glob.glob(pattern))
    return matches[0] if matches else None


def load_minute_bars(symbol: str, artifact_dirs: Iterable[str]) -> List[Dict[str, Any]]:
    """Load minute bars from local artifact CSVs if present.

    Expected columns: ts, open, high, low, close, volume.
    File name patterns are flexible to accommodate different producers.
    """
    sym = symbol.upper()
    patterns = [
        f"{sym}_bars.csv",
        f"{sym}_minute.csv",
        f"minute_bars_{sym}.csv",
        f"bars_{sym}.csv",
        f"{sym}_1m.csv",
    ]
    for d in artifact_dirs or []:
        if not d:
            continue
        for pat in patterns:
            for path in sorted(glob.glob(os.path.join(d, pat))):
                try:
                    out: List[Dict[str, Any]] = []
                    with open(path, newline="", encoding="utf-8") as f:
                        r = csv.DictReader(f)
                        for row in r:
                            try:
                                out.append(
                                    {
                                        "ts": row.get("ts") or row.get("timestamp") or row.get("time"),
                                        "open": float(row.get("open", 0) or 0),
                                        "high": float(row.get("high", 0) or 0),
                                        "low": float(row.get("low", 0) or 0),
                                        "close": float(row.get("close", 0) or 0),
                                        "volume": int(float(row.get("volume", 0) or 0)),
                                    }
                                )
                            except Exception:
                                continue
                    if out:
                        return out
                except Exception:
                    continue
    return []


def load_option_chain(symbol: str, search_dirs: Iterable[str]) -> List[ChainRow]:
    """Search multiple directories for a chain CSV and return parsed rows."""
    for d in search_dirs or []:
        if not d:
            continue
        # Prefer files that look like SYMBOL_YYYYMMDD.csv
        pattern = os.path.join(d, f"{symbol.upper()}_*.csv")
        candidates = sorted(glob.glob(pattern))
        # Filter to those whose suffix after '_' is all digits (likely an expiry tag)
        def _looks_like_chain(path: str) -> bool:
            base = os.path.basename(path)
            stem = os.path.splitext(base)[0]
            parts = stem.split("_")
            return len(parts) >= 2 and parts[-1].isdigit()

        for p in [c for c in candidates if _looks_like_chain(c)]:
            rows = load_chain_csv(p)
            if rows:
                return rows
    return []


def enrich_inplace(_rows: List[ScanRow], _cfg: Dict[str, object]) -> None:  # v1 with artifacts
    cfg: Dict[str, Any] = dict(_cfg)  # shallow copy only for typing
    data = cfg.get("data", {})
    mode = data.get("mode", "csv-only")
    # artifact/context
    artifact_dirs: List[str] = list(data.get("artifact_dirs", [])) or []
    cache_dir = None
    try:
        cache_dir = (data.get("cache", {}) or {}).get("dir") if isinstance(data.get("cache", {}), dict) else None
    except Exception:
        cache_dir = None
    if cache_dir and cache_dir not in artifact_dirs:
        artifact_dirs.append(str(cache_dir))
    chains_dir = data.get("chains_dir")

    offline = bool(data.get("offline", False))
    providers: List[str] = list(data.get("providers", ["ib", "yahoo"]))
    auto_producers = bool(data.get("auto_producers", False))
    upstream_timeout = int(data.get("upstream_timeout_sec", 30))

    # Halts map
    halts: Dict[str, int] = {}
    if not offline and (data.get("halts_source", "nasdaq") == "nasdaq"):
        try:
            halts = halts_nasdaq.get_halts_today(cfg)
        except Exception:
            halts = {}

    def set_field(row: Any, name: str, value: Any, src_key: str, src: str) -> None:
        if mode == "fetch" or getattr(row, name, None) in (None, ""):
            setattr(row, name, value)
            prov = getattr(row, "_provenance", None) or {}
            prov[src_key] = src
            setattr(row, "_provenance", prov)

    def try_ib(sym: str) -> Dict[str, Any]:
        try:
            return ib_provider.get_quote(sym, cfg)
        except Exception:
            return {}

    def try_yf_summary(sym: str) -> Dict[str, Any]:
        try:
            return yahoo_provider.get_summary(sym, cfg)
        except Exception:
            return {}

    def try_ib_bars(sym: str) -> List[Dict[str, Any]]:
        try:
            return ib_provider.get_intraday_bars(sym, cfg)
        except Exception:
            return []

    def try_yf_bars(sym: str) -> List[Dict[str, Any]]:
        try:
            return yahoo_provider.get_intraday_bars(sym, cfg)
        except Exception:
            return []

    def try_ib_chain(sym: str) -> List[Dict[str, Any]]:
        try:
            return ib_provider.get_option_chain(sym, cfg)
        except Exception:
            return []

    def try_yf_chain(sym: str) -> List[Dict[str, Any]]:
        try:
            return yahoo_provider.get_option_chain(sym, cfg)
        except Exception:
            return []

    def try_ib_shortable(sym: str) -> Dict[str, Any]:
        try:
            return ib_provider.get_shortable(sym, cfg)
        except Exception:
            return {"available": None, "fee_rate": None}

    for row in _rows:
        sym = getattr(row, "symbol").upper()
        errors: List[str] = []
        prov = getattr(row, "_provenance", None) or {}

        # Quotes
        q: Dict[str, Any] = {}
        ysum: Dict[str, Any] = {}
        for p in providers:
            if p == "ib" and not q:
                q = try_ib(sym)
                if q:
                    set_field(row, "last_price", q.get("last"), "src_last", "ib")
                    set_field(row, "prev_close", q.get("prev_close"), "src_prev_close", "ib")
            if p == "yahoo" and not ysum:
                ysum = try_yf_summary(sym)
                if ysum:
                    if getattr(row, "last_price", None) in (None, "") and ysum.get("last") is not None:
                        set_field(row, "last_price", ysum.get("last"), "src_last", "yahoo")
                    if getattr(row, "prev_close", None) in (None, "") and ysum.get("prev_close") is not None:
                        set_field(row, "prev_close", ysum.get("prev_close"), "src_prev_close", "yahoo")

        # Premarket gap
        if getattr(row, "premkt_gap_pct", None) in (None, ""):
            pm = ysum.get("pre_market_price") if ysum else None
            prev = getattr(row, "prev_close", None)
            try:
                if pm is not None and prev:
                    gap_pct = (float(pm) - float(prev)) / float(prev) * 100.0
                    set_field(row, "premkt_gap_pct", gap_pct, "src_gap", "yahoo")
                else:
                    if pm is None or prev is None:
                        errors.append("gap_unknown")
            except Exception:
                errors.append("gap_error")

        # Intraday bars → prefer artifacts, optionally auto‑produce, then providers
        bars: List[Dict[str, Any]] = []
        bars_src: Optional[str] = None
        # 1) artifacts
        try:
            bars = load_minute_bars(sym, artifact_dirs)
            if bars:
                bars_src = "artifact"
        except Exception:
            bars = []
        # 2) auto‑producers
        if not bars and auto_producers:
            try:
                from .upstream import run_live_bars

                if run_live_bars([sym], timeout=upstream_timeout):
                    bars = load_minute_bars(sym, artifact_dirs)
                    if bars:
                        bars_src = "artifact"
            except Exception:
                pass
        # 3) providers (only when not csv‑only)
        if not bars and mode != "csv-only":
            for p in providers:
                if p == "ib" and not bars:
                    bars = try_ib_bars(sym)
                    if bars:
                        bars_src = "ib"
                if p == "yahoo" and not bars:
                    bars = try_yf_bars(sym)
                    if bars:
                        bars_src = "yahoo"
        if bars:
            # Compute using the centralized pattern engine
            patt = compute_patterns(bars)
            # Last price from last bar if not present
            try:
                last_close = float(bars[-1].get("close", 0.0))
                if getattr(row, "last_price", None) in (None, "") and last_close > 0:
                    set_field(row, "last_price", last_close, "src_last", bars_src or prov.get("src_last", "yahoo"))
            except Exception:
                pass

            # Fill computed fields
            if patt.get("rvol_1m"):
                set_field(row, "rvol_1m", float(patt["rvol_1m"]), "src_rvol", bars_src or "yahoo")
            if patt.get("rvol_5m"):
                set_field(row, "rvol_5m", float(patt["rvol_5m"]), "src_rvol5", bars_src or "yahoo")
            if patt.get("vwap") is not None:
                set_field(row, "vwap", float(patt["vwap"]) if patt["vwap"] is not None else None, "src_vwap", bars_src or "yahoo")
            if patt.get("orb_high") is not None:
                set_field(row, "orb_high", float(patt["orb_high"]) if patt["orb_high"] is not None else None, "src_orb", bars_src or "yahoo")
            if patt.get("orb_low") is not None:
                set_field(row, "orb_low", float(patt["orb_low"]) if patt["orb_low"] is not None else None, "src_orb", bars_src or "yahoo")
            if patt.get("above_vwap_now"):
                set_field(row, "above_vwap_now", patt["above_vwap_now"], "src_above_vwap", bars_src or "yahoo")
            if patt.get("vwap_distance_pct") is not None:
                set_field(row, "vwap_distance_pct", float(patt["vwap_distance_pct"]), "src_vwap_dist", bars_src or "yahoo")
            if patt.get("pattern_signal") is not None:
                set_field(row, "pattern_signal", str(patt["pattern_signal"]), "src_pattern", bars_src or "yahoo")

        # Yahoo summary fundamentals → float/adv/short
        if ysum:
            fs = ysum.get("float_shares")
            if fs:
                set_field(row, "float_millions", float(fs) / 1e6, "src_float", "yahoo")
            av10 = ysum.get("avg_vol_10d") or 0
            av3m = ysum.get("avg_vol_3m") or 0
            lastp = getattr(row, "last_price", None) or 0
            if (av10 or av3m) and lastp:
                adv = max(int(av10 or 0), int(av3m or 0)) * float(lastp) / 1e6
                set_field(row, "adv_usd_millions", adv, "src_adv", "yahoo")
            spf = ysum.get("short_percent_float")
            if spf is not None:
                set_field(row, "short_interest_pct", float(spf), "src_short_interest", "yahoo")

        # Shortable
        if "ib" in providers and not offline:
            sdat = try_ib_shortable(sym)
            if sdat:
                if sdat.get("available") is not None:
                    set_field(row, "borrow_available", sdat.get("available"), "src_borrow", "ib")
                if sdat.get("fee_rate") is not None:
                    set_field(row, "borrow_rate_pct", sdat.get("fee_rate"), "src_borrow_rate", "ib")

        # Option chains → optionable + near money stats (artifacts → auto‑producers → providers)
        chain: List[Dict[str, Any]] = []
        chain_src: Optional[str] = None
        # 1) local files (explicit chains_dir first)
        try:
            # Prefer explicit chains_dir strictly to avoid matching unrelated CSVs
            search_dirs = [chains_dir] if chains_dir else artifact_dirs
            chain = load_option_chain(sym, search_dirs)
            if chain:
                chain_src = "artifact"
        except Exception:
            chain = []
        # 2) auto‑producers
        if not chain and auto_producers:
            try:
                from .upstream import run_chain_snapshot

                if run_chain_snapshot([sym], timeout=upstream_timeout):
                    chain = load_option_chain(sym, search_dirs)
                    if chain:
                        chain_src = "artifact"
            except Exception:
                pass
        # 3) providers
        if not chain and not offline and mode != "csv-only":
            for p in providers:
                if p == "ib" and not chain:
                    chain = try_ib_chain(sym)
                    if chain:
                        chain_src = "ib"
                if p == "yahoo" and not chain:
                    chain = try_yf_chain(sym)
                    if chain:
                        chain_src = "yahoo"
        if chain:
            set_field(row, "optionable", "Yes", "src_chain", chain_src or (providers[0] if providers else "provider"))
            spot = getattr(row, "last_price", None) or getattr(row, "price", None) or 0
            if spot:
                oi, spr = near_money_stats(chain, float(spot), 3.0)
                set_field(row, "oi_near_money", oi, "src_chain_oi", chain_src or (providers[0] if providers else "provider"))
                if spr is not None:
                    set_field(row, "spread_pct_near_money", spr, "src_chain_spread", chain_src or (providers[0] if providers else "provider"))
            # Expose fetched chain rows to downstream consumers (e.g., structure picker)
            try:
                setattr(row, "_chain_rows", chain)
            except Exception:
                pass

        # Halts
        if halts:
            set_field(row, "halts_count_today", int(halts.get(sym, 0)), "src_halts", "nasdaq")

        if errors:
            setattr(row, "_data_errors", errors)
        if prov:
            setattr(row, "_provenance", {**prov, **getattr(row, "_provenance", {})})

    return None


def near_money_stats(chain_rows: List[Dict[str, Any]] | List[ChainRow], spot: float, pct: float = 3.0) -> Tuple[int, Optional[float]]:
    lo = spot * (1.0 - pct / 100.0)
    hi = spot * (1.0 + pct / 100.0)
    total_oi = 0
    spreads: List[float] = []
    for r in chain_rows:
        # support both dataclass and plain dict rows without evaluating defaults eagerly
        strike = float(getattr(r, "strike", float(r["strike"])) if isinstance(r, dict) else getattr(r, "strike", 0.0))  # type: ignore[index]
        if lo <= strike <= hi:
            if isinstance(r, dict):
                bid = float(r.get("bid", 0.0))
                ask = float(r.get("ask", 0.0))
                oi = int(float(r.get("oi", 0)))
            else:
                bid = float(getattr(r, "bid", 0.0))
                ask = float(getattr(r, "ask", 0.0))
                oi = int(getattr(r, "oi", 0))
            mid = (bid + ask) / 2 if (bid > 0 and ask > 0) else max(bid, ask)
            if mid > 0 and ask > 0 and bid > 0:
                spreads.append((ask - bid) / mid)
            total_oi += oi
    avg_spread = (sum(spreads) / len(spreads)) if spreads else None
    return total_oi, avg_spread
