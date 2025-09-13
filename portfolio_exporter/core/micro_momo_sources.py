from __future__ import annotations

import csv
import glob
import os
from typing import Dict, Iterable, List, Optional, Tuple, Any

from .micro_momo_types import ChainRow, ScanRow
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


def enrich_inplace(_rows: List[ScanRow], _cfg: Dict[str, object]) -> None:  # v1 no-op
    cfg: Dict[str, Any] = dict(_cfg)  # shallow copy only for typing
    data = cfg.get("data", {})
    mode = data.get("mode", "csv-only")
    if mode == "csv-only":
        return None

    offline = bool(data.get("offline", False))
    providers: List[str] = list(data.get("providers", ["ib", "yahoo"]))

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

        # Intraday bars → RVOL, VWAP, ORB
        bars: List[Dict[str, Any]] = []
        for p in providers:
            if p == "ib" and not bars:
                bars = try_ib_bars(sym)
            if p == "yahoo" and not bars:
                bars = try_yf_bars(sym)
        if bars:
            vols = [b.get("volume", 0) for b in bars]
            mean_vol = (sum(vols) / max(1, len(vols))) if vols else 0.0
            last1 = sum(vols[-1:])
            last5 = sum(vols[-5:])
            if mean_vol > 0:
                set_field(row, "rvol_1m", last1 / mean_vol, "src_rvol", prov.get("src_rvol", "ib" if providers and providers[0] == "ib" else "yahoo"))
                set_field(row, "rvol_5m", last5 / (mean_vol * min(5, len(vols))), "src_rvol5", prov.get("src_rvol5", "ib" if providers and providers[0] == "ib" else "yahoo"))
            # VWAP
            pv = 0.0
            tv = 0.0
            for b in bars:
                c = float(b.get("close", 0.0))
                v = float(b.get("volume", 0.0))
                pv += c * v
                tv += v
            if tv > 0:
                set_field(row, "vwap", pv / tv, "src_vwap", prov.get("src_vwap", "ib" if providers and providers[0] == "ib" else "yahoo"))
            # ORB using first up to 5 bars
            orb_bars = bars[: min(5, len(bars))]
            if orb_bars:
                hi = max(b.get("high", b.get("close", 0.0)) for b in orb_bars)
                lo = min(b.get("low", b.get("close", 0.0)) for b in orb_bars)
                set_field(row, "orb_high", hi, "src_orb", prov.get("src_orb", "ib" if providers and providers[0] == "ib" else "yahoo"))
                set_field(row, "orb_low", lo, "src_orb", prov.get("src_orb", "ib" if providers and providers[0] == "ib" else "yahoo"))
            # Last price from last bar if not present
            try:
                last_close = float(bars[-1].get("close", 0.0))
                if getattr(row, "last_price", None) in (None, "") and last_close > 0:
                    set_field(row, "last_price", last_close, "src_last", prov.get("src_last", "yahoo"))
            except Exception:
                pass
            # Derived signals: above VWAP now and simple pattern
            try:
                last_close = float(bars[-1].get("close", 0.0))
                vwap = getattr(row, "vwap", None)
                if isinstance(vwap, (int, float)) and vwap > 0:
                    set_field(row, "above_vwap_now", "Yes" if last_close >= float(vwap) else "No", "src_above_vwap", prov.get("src_vwap", "yahoo"))
                # Pattern: 'orb' if last close breaks ORB high; 'reclaim' if first close below VWAP and last above
                first_close = float(bars[0].get("close", 0.0)) if bars else 0.0
                orb_hi = getattr(row, "orb_high", None)
                patt = None
                if isinstance(orb_hi, (int, float)) and orb_hi and last_close > float(orb_hi):
                    patt = "orb"
                elif isinstance(vwap, (int, float)) and vwap and first_close < float(vwap) <= last_close:
                    patt = "reclaim"
                if patt:
                    set_field(row, "pattern_signal", patt, "src_pattern", prov.get("src_vwap", "yahoo"))
            except Exception:
                pass

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

        # Option chains → optionable + near money stats
        chain: List[Dict[str, Any]] = []
        if not offline:
            for p in providers:
                if p == "ib" and not chain:
                    chain = try_ib_chain(sym)
                if p == "yahoo" and not chain:
                    chain = try_yf_chain(sym)
        if chain:
            set_field(row, "optionable", "Yes", "src_chain", providers[0])
            spot = getattr(row, "last_price", None) or getattr(row, "price", None) or 0
            if spot:
                oi, spr = near_money_stats(chain, float(spot), 3.0)
                set_field(row, "oi_near_money", oi, "src_chain_oi", providers[0])
                if spr is not None:
                    set_field(row, "spread_pct_near_money", spr, "src_chain_spread", providers[0])
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
        strike = float(getattr(r, "strike", r.get("strike")))  # type: ignore[attr-defined]
        if lo <= strike <= hi:
            bid = float(getattr(r, "bid", r.get("bid", 0.0)))  # type: ignore[attr-defined]
            ask = float(getattr(r, "ask", r.get("ask", 0.0)))  # type: ignore[attr-defined]
            mid = (bid + ask) / 2 if (bid > 0 and ask > 0) else max(bid, ask)
            if mid > 0 and ask > 0 and bid > 0:
                spreads.append((ask - bid) / mid)
            oi = int(getattr(r, "oi", r.get("oi", 0)))  # type: ignore[attr-defined]
            total_oi += oi
    avg_spread = (sum(spreads) / len(spreads)) if spreads else None
    return total_oi, avg_spread
