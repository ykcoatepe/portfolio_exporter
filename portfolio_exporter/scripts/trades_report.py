#!/usr/bin/env python3


from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import glob
import math
from zoneinfo import ZoneInfo
from pathlib import Path
import os
import argparse
import json
import sys

from portfolio_exporter.core.config import settings
try:  # optional IBKR config
    from portfolio_exporter.core.ib_config import HOST as IB_HOST, PORT as IB_PORT, client_id as _cid
except Exception:  # pragma: no cover - fallback defaults
    IB_HOST = "127.0.0.1"  # type: ignore
    IB_PORT = 7497  # type: ignore

    def _cid(name: str, default: int = 0) -> int:  # type: ignore
        return default

from typing import Iterable, List, Tuple
from typing import Optional, Any, Dict

import pandas as pd
import numpy as np
import logging

from portfolio_exporter.core import combo as combo_core
from portfolio_exporter.core import io as io_core
from portfolio_exporter.core import io as core_io
from portfolio_exporter.core import config as config_core
from portfolio_exporter.core import cli as cli_helpers
from portfolio_exporter.core import json as json_helpers
from portfolio_exporter.core.runlog import RunLog

# Reuse enrichment from portfolio_greeks to keep behavior identical
try:
    from portfolio_exporter.scripts.portfolio_greeks import (  # type: ignore
        _enrich_combo_strikes as _enrich_combo_strikes_greeks,
    )
except Exception:  # pragma: no cover - defensive import fallback
    _enrich_combo_strikes_greeks = None  # type: ignore

logger = logging.getLogger(__name__)

try:
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate,
        Table,
        TableStyle,
        Paragraph,
        Spacer,
        PageBreak,
    )
    from reportlab.lib.styles import getSampleStyleSheet
except Exception:  # pragma: no cover - optional
    (
        SimpleDocTemplate,
        Table,
        TableStyle,
        Paragraph,
        Spacer,
        PageBreak,
        getSampleStyleSheet,
        colors,
        letter,
        landscape,
    ) = (None,) * 10
import calendar

try:  # optional dependency
    from ib_insync import IB, ExecutionFilter  # type: ignore
except Exception:  # pragma: no cover - optional
    IB = None  # type: ignore
    ExecutionFilter = None  # type: ignore

# Give the user a clear hint if ib_insync is missing
if IB is None:
    print(
        "❌  ib_insync library not found. Install with:\n"
        "    pip install ib_insync\n"
        "and ensure the Interactive Brokers TWS or IB Gateway is running with "
        "API enabled.",
        file=sys.stderr,
    )


LIQ_MAP = {1: "Added", 2: "Removed", 3: "RoutedOut", 4: "Auction"}


# ───────────────────────── intent helpers (timestamps, matching) ─────────────────────────
# Expanded timestamp candidates to catch varied CSVs
_TS_COL_CANDIDATES = (
    "datetime",
    "timestamp",
    "time",
    "date",
    "exec_time",
    "Date/Time",
    "TradeTime",
    "fill_time",
    "timestamp_utc",
)


def _parse_ts_any(val) -> datetime | None:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    try:
        ts = pd.to_datetime(val, utc=True, errors="coerce")
        if pd.isna(ts):
            return None
        return ts.to_pydatetime() if isinstance(ts, pd.Timestamp) else None
    except Exception:
        return None


def _get_earliest_exec_ts(df: pd.DataFrame) -> datetime | None:
    if df is None or df.empty:
        return None
    best: datetime | None = None
    for col in _TS_COL_CANDIDATES:
        if col in df.columns:
            try:
                ts = pd.to_datetime(df[col], utc=True, errors="coerce").min(skipna=True)
                if isinstance(ts, pd.Timestamp) and not pd.isna(ts):
                    dt = ts.to_pydatetime()
                    best = dt if best is None or dt < best else best
            except Exception:
                continue
    return best


def _normalize_expiry(val) -> str | None:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    try:
        t = pd.to_datetime(val, utc=False, errors="coerce")
        if pd.isna(t):
            return None
        return t.date().isoformat()
    except Exception:
        return None


def _iter_positions_candidates(outdir_path: Path) -> list[tuple[Path, float]]:
    paths = sorted(outdir_path.glob("portfolio_greeks_positions*.csv"))
    out: list[tuple[Path, float]] = []
    for p in paths:
        # try to parse timestamp from filename: portfolio_greeks_positions_YYYYMMDD_HHMM.csv
        try:
            name = p.name
            m = pd.Series([name]).str.extract(r"(\d{8})[\-_]?(\d{4})").iloc[0]
            if isinstance(m, pd.Series) and not m.isna().any():
                dt = datetime.strptime(str(m[0]) + str(m[1]), "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
                out.append((p, dt.timestamp()))
                continue
        except Exception:
            pass
        # fallback to mtime
        try:
            out.append((p, p.stat().st_mtime))
        except Exception:
            continue
    return out


def _find_positions_before_many(cutoff: datetime | None, search_dirs: list[Path]) -> Path | None:
    all_cands: list[tuple[Path, float]] = []
    for d in search_dirs:
        try:
            if d and d.exists():
                all_cands.extend(_iter_positions_candidates(d))
        except Exception:
            continue
    if not all_cands:
        return None
    if cutoff is None:
        return max(all_cands, key=lambda t: t[1])[0]
    cut = cutoff.timestamp()
    older = [p for (p, ts) in all_cands if ts < cut]
    if not older:
        return None
    return max(older, key=lambda p: p.stat().st_mtime)


def _match_leg_in_prior(leg: dict, prior_df: pd.DataFrame, strike_tol: float = 0.01) -> tuple[bool, str, float]:
    if prior_df is None or prior_df.empty:
        return False, "no_match", 0.0
    try:
        u = str(leg.get("underlying") or "")
        e = _normalize_expiry(leg.get("expiry")) or ""
        r = str(leg.get("right") or "").upper()
        try:
            k = float(leg.get("strike")) if leg.get("strike") is not None else None
        except Exception:
            k = None
        df = prior_df.copy()
        for c in ("strike", "qty"):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        if "right" in df.columns:
            df["right"] = df["right"].astype(str).str.upper()
        if "underlying" in df.columns:
            df["underlying"] = df["underlying"].astype(str)
        if "expiry" in df.columns:
            df["__exp"] = df["expiry"].apply(_normalize_expiry)
        m = (df.get("underlying") == u) & (df.get("right") == r)
        if e:
            m &= (df.get("__exp") == e)
        if k is not None:
            m &= (df.get("strike").sub(k).abs() <= strike_tol)
        cand = df.loc[m]
        if not cand.empty:
            q = float(pd.to_numeric(cand.get("qty"), errors="coerce").fillna(0).sum())
            return (q != 0.0), "attr_tol", q
    except Exception:
        return False, "no_match", 0.0
    return False, "no_match", 0.0


def _ensure_prev_positions_quiet(
    earliest_exec_ts: datetime | None,
    outdir: Path,
    prior_override: str | None = None,
    search_dirs: list[Path] | None = None,
) -> tuple[pd.DataFrame, Path | None]:
    """Prefer a snapshot strictly older than earliest execution; fallback to latest.

    Returns (DataFrame, path_or_none).
    """
    # explicit override
    if prior_override:
        p = Path(prior_override).expanduser()
        if p.exists():
            try:
                return pd.read_csv(p), p
            except Exception:
                pass
    dirs: list[Path] = []
    if search_dirs:
        dirs.extend([Path(d) for d in search_dirs])
    # Always include provided outdir and default settings dir
    if outdir:
        dirs.append(Path(outdir))
    try:
        from pathlib import Path as _P
        default_dir = _P(config_core.settings.output_dir)
        if default_dir not in dirs:
            dirs.append(default_dir)
        tests_dir = _P("tests/data")
        if tests_dir.exists():
            dirs.append(tests_dir)
    except Exception:
        pass

    # strictly prior
    try:
        p = _find_positions_before_many(earliest_exec_ts, dirs)
        if p and p.exists():
            try:
                return pd.read_csv(p), p
            except Exception:
                pass
    except Exception:
        pass

    # fallback latest per dir
    for d in dirs:
        try:
            latest = io_core.latest_file("portfolio_greeks_positions", outdir=d)
            if latest and latest.exists():
                try:
                    return pd.read_csv(latest), latest
                except Exception:
                    continue
        except Exception:
            continue
    return pd.DataFrame(), None


def _intent_counts(series: "pd.Series|None") -> dict[str, int]:
    effects = ["Open", "Close", "Roll", "Mixed", "Unknown"]
    if series is None:
        return {e: 0 for e in effects}
    try:
        s = series.dropna().astype(str)
    except Exception:
        return {e: 0 for e in effects}
    return {e: int((s == e).sum()) for e in effects}


def _attach_intent_flags(df: "pd.DataFrame") -> "pd.DataFrame":
    if df is None or df.empty:
        return df
    col = "position_effect"
    if col not in df.columns:
        df[col] = "Unknown"
    for e, name in [
        ("Open", "is_open"),
        ("Close", "is_close"),
        ("Roll", "is_roll"),
        ("Mixed", "is_mixed"),
    ]:
        try:
            df[name] = (df[col].astype(str) == e).astype(int)
        except Exception:
            df[name] = 0
    return df


def _choose_underlying_effect(g: "pd.DataFrame") -> str:
    vals = g.get("position_effect", pd.Series([], dtype=str)).astype(str).tolist()
    if any(v == "Roll" for v in vals):
        return "Roll"
    if vals and all(v == "Close" for v in vals):
        return "Close"
    if vals and all(v == "Open" for v in vals):
        return "Open"
    if any(v == "Mixed" for v in vals):
        return "Mixed"
    return "Unknown"
# ───── Lightweight executions loader & action classifier ─────
def _load_trades() -> pd.DataFrame | None:
    """Fetch executed trades from IBKR.

    Raises
    ------
    RuntimeError
        If ib_insync is not available or IB API cannot be used.

    Returns
    -------
    DataFrame | None
        DataFrame of executions. Tests may monkeypatch this function and
        return a prebuilt DataFrame.
    """
    if IB is None or ExecutionFilter is None:
        raise RuntimeError(
            "❌ ib_insync library not found or IB ExecutionFilter unavailable. "
            "Install with: pip install ib_insync and ensure the IB Gateway/TWS is running with API enabled."
        )

    start, end = prompt_date_range()
    trades, _open_orders = fetch_trades_ib(start, end)
    trades = filter_trades(trades, start, end)
    df = pd.DataFrame([t.__dict__ for t in trades])
    if df.empty:
        print("⚠ No executions found for that period.")
        return pd.DataFrame()
    return df


def _load_open_orders() -> pd.DataFrame:
    # Use optional top-level IB binding; return empty if unavailable
    if IB is None:
        return pd.DataFrame()
    ib = IB()
    try:
        ib.connect(IB_HOST, IB_PORT, clientId=IB_OPEN_CID, timeout=5)
    except Exception as exc:  # pragma: no cover - connection optional
        logger.warning("IBKR connection failed for open orders: host=%s port=%s cid=%s err=%s", IB_HOST, IB_PORT, IB_OPEN_CID, exc)
        return pd.DataFrame()

    rows = []
    for o in ib.openOrders():
        c = o.contract
        rows.append(
            {
                "PermId": o.permId,
                "OrderId": o.orderId,
                "symbol": c.symbol,
                "secType": c.secType,
                "Side": o.action.upper(),
                "Qty": o.totalQuantity,
                "Price": getattr(o, "lmtPrice", np.nan),
                "OrderRef": o.orderRef or "",
                "Liquidation": 0,
                "lastLiquidity": 0,
                "Action": "Open",
            }
        )
    ib.disconnect()
    return pd.DataFrame(rows)


def _classify(row: pd.Series) -> str:
    sec = str(row.get("secType", ""))
    side = str(row.get("Side", ""))
    try:
        liq = int(row.get("Liquidation", 0))
    except Exception:
        liq = 0
    try:
        lastliq = int(row.get("lastLiquidity", 0))
    except Exception:
        lastliq = 0
    ref = str(row.get("OrderRef", ""))
    ref = ref if ref is not None else ""
    ref = ref.upper()

    if sec == "BAG":
        return "Combo"
    if "ROLL" in ref:
        return "Roll"
    if liq > 0 or lastliq in {2, 4}:
        return "Close"
    return "Buy" if side == "BOT" else "Sell"


def _prior_qty_for_row(row: pd.Series, prev_positions: pd.DataFrame | None, strike_tol: float = 0.05) -> tuple[float, str]:
    """
    Best-effort prior quantity lookup for a single execution row against prev_positions.

    Returns (prior_qty, match_mode) where match_mode ∈ {'id','attr_exact','attr_tol','no_match'}.
    """
    try:
        if prev_positions is None or not isinstance(prev_positions, pd.DataFrame) or prev_positions.empty:
            return 0.0, "no_match"

        sym = str(row.get("symbol") or row.get("underlying") or "").upper()
        exp = None
        try:
            exp = pd.to_datetime(row.get("expiry"), errors="coerce").date().isoformat()
        except Exception:
            pass
        rgt = str(row.get("right") or "").upper()
        try:
            k = float(row.get("strike")) if row.get("strike") is not None else None
        except Exception:
            k = None

        p = prev_positions.copy()
        for c in ("strike", "qty"):
            if c in p.columns:
                p[c] = pd.to_numeric(p[c], errors="coerce")
        if "right" in p.columns:
            p["right"] = p["right"].astype(str).str.upper()
        if "underlying" in p.columns:
            p["underlying"] = p["underlying"].astype(str).str.upper()
        if "expiry" in p.columns:
            p["__exp"] = pd.to_datetime(p["expiry"], errors="coerce").dt.date.astype(str)

        # ID-based first
        try:
            cid = row.get("conId") or row.get("conid")
            if cid is not None and "conId" in p.columns:
                pc = p[p["conId"] == pd.to_numeric(cid, errors="coerce")]
                if not pc.empty:
                    q = float(pd.to_numeric(pc.get("qty"), errors="coerce").fillna(0).sum())
                    return q, "id"
        except Exception:
            pass

        # Attribute exact on rounded strike
        m = (p.get("underlying") == sym)
        if exp:
            m &= (p.get("__exp") == exp)
        if rgt:
            m &= (p.get("right") == rgt)
        if k is not None and "strike" in p.columns:
            try:
                k2 = float(f"{float(k):.2f}")
                m_exact = m & (p["strike"].apply(lambda x: float(f"{float(x):.2f}") if pd.notna(x) else float("nan")) == k2)
                pc = p[m_exact]
                if not pc.empty:
                    q = float(pd.to_numeric(pc.get("qty"), errors="coerce").fillna(0).sum())
                    return q, "attr_exact"
            except Exception:
                pass

        # Attribute tolerance
        if k is not None and "strike" in p.columns:
            try:
                m_tol = m & (p["strike"].sub(float(k)).abs() <= float(strike_tol))
                pc = p[m_tol]
                if not pc.empty:
                    q = float(pd.to_numeric(pc.get("qty"), errors="coerce").fillna(0).sum())
                    return q, "attr_tol"
            except Exception:
                pass

        return 0.0, "no_match"
    except Exception:
        return 0.0, "no_match"


def _infer_position_effect(row: pd.Series, prev_positions: pd.DataFrame | None = None) -> str:
    """
    Best-effort position effect labeling for a single execution row.

    Precedence:
    1) Explicit hints:
       - OrderRef contains 'ROLL' => Roll
       - openClose ('O'/'C'), or Action=='Open' => Open/Close
    2) Prior snapshot presence + Side:
       - BUY/BOT reduces short => Close; else Open
       - SELL/SLD reduces long  => Close; else Open
    3) Default to Open (visibility over Unknown when prior is absent)
    """
    u = lambda x: str(x or "").strip().upper()

    # 1) Strong explicit signals
    if "ROLL" in u(row.get("OrderRef") or row.get("order_ref")):
        return "Roll"
    oc = u(row.get("openClose"))
    if oc in {"O", "OPEN"}:
        return "Open"
    if oc in {"C", "CLOSE"}:
        return "Close"
    if u(row.get("Action")) == "OPEN":
        return "Open"

    # 2) Prior snapshot comparison + side
    side = u(row.get("Side") or row.get("side"))
    prior_qty, _mode = _prior_qty_for_row(row, prev_positions, strike_tol=0.05)

    if side in {"BUY", "BOT"}:
        if prior_qty < 0:
            return "Close"
        return "Open"
    if side in {"SELL", "SLD"}:
        if prior_qty > 0:
            return "Close"
        return "Open"

    # 3) Default
    return "Open"


def _infer_position_effect_safe(prev_df):
    """Return a per-row safe wrapper so one bad row doesn't break the column."""
    def _inner(row: pd.Series) -> str:
        try:
            val = _infer_position_effect(row, prev_df)
            return str(val) if val is not None else "Unknown"
        except Exception:
            return "Unknown"
    return _inner


def _compute_streaming_effect(df: pd.DataFrame, prev_positions: pd.DataFrame | None) -> pd.Series:
    """
    Vectorized per-row intent classification using streaming deltas per instrument.

    For each instrument key K = (underlying, safe_expiry, right, round2(strike)):
      pre  = prior_qty(K) + cumsum(delta(K)) up to before the row
      post = pre + delta(row)
      effect = 'Close' if |post| < |pre| else 'Open'

    Rows without a valid key fall back to the row-wise safe classifier.
    """
    if df is None or df.empty:
        return pd.Series([], dtype=str)

    d = df.copy()
    d["__orig_idx"] = df.index.values

    # Signed delta from side/qty
    if "qty" in d.columns:
        q = d["qty"]
    elif "Qty" in d.columns:
        q = d["Qty"]
    elif "total_qty" in d.columns:
        q = d["total_qty"]
    else:
        q = pd.Series([np.nan] * len(d))
    side = d.get("Side", d.get("side")).astype(str).str.upper()
    sign = side.map({"BUY": 1, "BOT": 1, "SELL": -1, "SLD": -1}).fillna(0)
    d["__delta"] = pd.to_numeric(q, errors="coerce").fillna(0).astype(float) * sign

    # Instrument key
    sym = d.get("symbol", d.get("underlying"))
    d["__sym"] = sym.astype(str).str.upper()
    d["__exp"] = pd.to_datetime(d.get("expiry"), errors="coerce").dt.date.astype(str)
    d["__right"] = d.get("right").astype(str).str.upper()
    d["__k2"] = pd.to_numeric(d.get("strike"), errors="coerce").apply(lambda x: float(f"{x:.2f}") if pd.notna(x) else np.nan)
    d["__ts"] = pd.to_datetime(d.get("datetime"), errors="coerce")
    d["__key_valid"] = d["__sym"].ne("") & d["__right"].isin(["C", "P"]) & d["__exp"].ne("NaT") & d["__k2"].notna()

    # Prior map
    prior_map: dict[tuple, float] = {}
    if isinstance(prev_positions, pd.DataFrame) and not prev_positions.empty:
        p = prev_positions.copy()
        p["__sym"] = p.get("underlying").astype(str).str.upper()
        p["__exp"] = pd.to_datetime(p.get("expiry"), errors="coerce").dt.date.astype(str)
        p["__right"] = p.get("right").astype(str).str.upper()
        p["__k2"] = pd.to_numeric(p.get("strike"), errors="coerce").apply(lambda x: float(f"{x:.2f}") if pd.notna(x) else np.nan)
        p["qty"] = pd.to_numeric(p.get("qty"), errors="coerce").fillna(0.0)
        prior_map = p.groupby(["__sym", "__exp", "__right", "__k2"], dropna=False)["qty"].sum().to_dict()

    d["__key"] = list(zip(d["__sym"], d["__exp"], d["__right"], d["__k2"]))
    d = d.sort_values(["__key", "__ts", "__orig_idx"])  # stable order

    effects = pd.Series(index=d["__orig_idx"], dtype=object)

    for key, g in d.groupby("__key", dropna=False, sort=False):
        valid = g["__key_valid"].astype(bool)
        if not valid.any():
            # Fallback for incomplete key
            for idx in g.index:
                effects.at[d.loc[idx, "__orig_idx"]] = _infer_position_effect(df.loc[d.loc[idx, "__orig_idx"]], prev_positions)
            continue

        prior = float(prior_map.get(key, 0.0))
        csum = g["__delta"].cumsum()
        pre = prior + csum - g["__delta"]
        post = pre + g["__delta"]
        eff = np.where(np.abs(post) < np.abs(pre), "Close", "Open")
        for idx2, label in zip(g.index, eff):
            effects.at[d.loc[idx2, "__orig_idx"]] = str(label)

    effects = effects.reindex(df.index)
    miss = effects[effects.isna()].index
    if len(miss) > 0:
        effects.loc[miss] = df.loc[miss].apply(_infer_position_effect_safe(prev_positions), axis=1)
    return effects.astype(str)


@dataclass
class Trade:
    # execution identifiers
    exec_id: str
    perm_id: int
    order_id: int

    # contract fields
    symbol: str
    sec_type: str
    currency: str
    expiry: str | None
    strike: float | None
    right: str | None
    multiplier: int | None
    exchange: str
    primary_exchange: str | None
    trading_class: str | None
    combo_legs: List[dict] | None

    # fill details
    datetime: datetime
    side: str
    qty: int
    price: float
    avg_price: float
    cum_qty: int
    last_liquidity: str

    # commission / pnl
    commission: float | None
    commission_currency: str | None
    realized_pnl: float | None
    account: str | None
    model_code: str | None
    order_ref: str | None
    # IB execution position effect if available ("O"/"C").
    open_close: str | None


@dataclass
class OpenOrder:
    order_id: int
    perm_id: int
    symbol: str
    sec_type: str
    currency: str
    expiry: str | None
    strike: float | None
    right: str | None
    combo_legs: List[dict] | None
    side: str
    total_qty: int
    lmt_price: float | None
    aux_price: float | None
    tif: str | None
    order_type: str
    algo_strategy: str | None
    status: str
    filled: int
    remaining: int
    account: str | None
    order_ref: str | None


# ───────────────────────── CONFIG ──────────────────────────
# Use Türkiye local time (Europe/Istanbul) for timestamp tags
IB_CID = _cid("trades_report", default=5)
IB_OPEN_CID = _cid("trades_report_open", default=19)


MONTH_MAP = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTH_MAP.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})


def date_range_from_phrase(phrase: str, ref: date | None = None) -> Tuple[date, date]:
    phrase = phrase.strip().lower()
    ref = ref or date.today()

    if phrase in {"today"}:
        return ref, ref
    if phrase == "yesterday":
        y = ref - timedelta(days=1)
        return y, y
    if phrase in {"week", "week to date", "week-to-date", "wtd"}:
        start = ref - timedelta(days=ref.weekday())
        return start, ref
    if re.fullmatch(r"\d{4}", phrase):
        year = int(phrase)
        return date(year, 1, 1), date(year, 12, 31)

    m = re.fullmatch(r"([a-zA-Z]+)\s*(\d{4})?", phrase)
    if m and m.group(1).lower() in MONTH_MAP:
        month = MONTH_MAP[m.group(1).lower()]
        year = int(m.group(2)) if m.group(2) else ref.year
        last = calendar.monthrange(year, month)[1]
        return date(year, month, 1), date(year, month, last)

    dt = pd.to_datetime(phrase, errors="coerce")
    if pd.notnull(dt):
        d = dt.date()
        return d, d
    raise ValueError(f"Unrecognised date phrase: {phrase}")


# ─────────────────── interactive date‑range prompt ───────────────────
def prompt_date_range() -> Tuple[date, date]:
    """
    Ask the user which range to pull (today / yesterday / week / custom).
    Returns a (start, end) date tuple.
    """
    print("\nSelect trade‑log range:")
    print("  1  Today")
    print("  2  Yesterday")
    print("  3  Week‑to‑date")
    print("  4  Custom (YYYY‑MM‑DD or phrase e.g. 'June 2024')")
    while True:
        choice = input("Enter choice [1‑4]: ").strip()
        if choice == "1":
            return date_range_from_phrase("today")
        if choice == "2":
            return date_range_from_phrase("yesterday")
        if choice == "3":
            return date_range_from_phrase("week")
        if choice == "4":
            phrase = input("Enter date / phrase: ").strip()
            try:
                return date_range_from_phrase(phrase)
            except ValueError as e:
                print(f"  ⚠ {e}")
                continue
        print("  ⚠ Invalid choice; try again.")


def filter_trades(trades: Iterable[Trade], start: date, end: date) -> List[Trade]:
    return [t for t in trades if start <= t.datetime.date() <= end]


def fetch_trades_ib(start: date, end: date) -> Tuple[List[Trade], List[OpenOrder]]:
    """
    Return (trades, open_orders) within [start, end] inclusive.
    Uses execDetails / commissionReport / openOrder callbacks.
    """
    if IB is None or ExecutionFilter is None:
        return [], []

    ib = IB()

    try:
        ib.connect(IB_HOST, IB_PORT, clientId=IB_CID, timeout=10)
    except Exception as exc:
        # Align with other scripts: downgrade to a warning and continue offline
        logger.warning(
            "IBKR connection failed for executions: host=%s port=%s cid=%s err=%s",
            IB_HOST,
            IB_PORT,
            IB_CID,
            exc,
        )
        return [], []

    # --- Capture executions & commission reports ------------------------------
    # Annotate with Any to avoid runtime dependency on ib_insync type names
    comm_map: dict[str, Any] = {}

    # CommissionReport only comes via callback; cache them by execId
    def _comm(*args):
        report = args[-1]  # CommissionReport is always last arg
        comm_map[report.execId] = report

    ib.commissionReportEvent += _comm

    all_execs: list[Any] = []
    day = start
    while day <= end:
        next_day = day + timedelta(days=1)
        filt = ExecutionFilter(
            time=day.strftime("%Y%m%d 00:00:00"), clientId=0, acctCode=""
        )
        all_execs.extend(ib.reqExecutions(filt))
        day = next_day
    print(f"[INFO] pulled {len(all_execs)} executions between {start} and {end}")
    ib.sleep(0.3)  # brief pause so CommissionReport callbacks arrive
    ib.commissionReportEvent -= _comm

    execs = [(det.contract, det.execution) for det in all_execs]

    # --- Build Trade objects ---------------------------------------------------
    trades: List[Trade] = []
    for contract, ex in execs:
        exec_dt = pd.to_datetime(ex.time).to_pydatetime()
        if not (start <= exec_dt.date() <= end):
            continue

        # ensure contract is qualified for full fields
        if not contract.conId:
            (qualified,) = ib.qualifyContracts(contract)
            contract = qualified

        combo_legs_data = []
        if contract.secType == "BAG" and contract.comboLegs:
            from ib_insync import Contract

            for leg in contract.comboLegs:
                # For combo legs, we need to qualify each leg's contract to get details like symbol, expiry, strike, right
                leg_contract = ib.qualifyContracts(
                    Contract(conId=leg.conId, exchange=leg.exchange)
                )[0]
                combo_legs_data.append(
                    {
                        "symbol": leg_contract.symbol,
                        "sec_type": leg_contract.secType,
                        "expiry": getattr(
                            leg_contract, "lastTradeDateOrContractMonth", None
                        ),
                        "strike": getattr(leg_contract, "strike", None),
                        "right": getattr(leg_contract, "right", None),
                        "ratio": leg.ratio,
                        "action": leg.action,
                        "exchange": leg.exchange,
                    }
                )

        comm = comm_map.get(ex.execId, None)
        trades.append(
            Trade(
                exec_id=ex.execId,
                perm_id=ex.permId,
                order_id=ex.orderId,
                symbol=contract.symbol,
                sec_type=contract.secType,
                currency=contract.currency,
                expiry=getattr(contract, "lastTradeDateOrContractMonth", None),
                strike=getattr(contract, "strike", None),
                right=getattr(contract, "right", None),
                multiplier=(
                    int(contract.multiplier)
                    if getattr(contract, "multiplier", None)
                    else None
                ),
                exchange=ex.exchange,
                primary_exchange=getattr(contract, "primaryExchange", None),
                trading_class=getattr(contract, "tradingClass", None),
                combo_legs=combo_legs_data if combo_legs_data else None,
                datetime=exec_dt,
                side="BUY" if ex.side.upper() == "BOT" else "SELL",
                qty=int(ex.shares),
                price=ex.price,
                avg_price=ex.avgPrice,
                cum_qty=ex.cumQty,
                last_liquidity=LIQ_MAP.get(ex.lastLiquidity, str(ex.lastLiquidity)),
                commission=comm.commission if comm else None,
                commission_currency=comm.currency if comm else None,
                realized_pnl=comm.realizedPNL if comm else None,
                account=ex.acctNumber,
                model_code=ex.modelCode,
                order_ref=ex.orderRef,
                open_close=getattr(ex, "openClose", None),
            )
        )

    # --- Capture open orders ---------------------------------------------------
    ib.reqAllOpenOrders()
    ib.sleep(1.5)  # allow gateway to populate the cache; was 0.6
    open_trades_snapshot: List["Trade"] = ib.openTrades()

    open_orders: List[OpenOrder] = []
    for tr in open_trades_snapshot:
        c = tr.contract
        o = tr.order
        status = tr.orderStatus

        combo_legs_data = []
        if c.secType == "BAG" and c.comboLegs:
            from ib_insync import Contract

            for leg in c.comboLegs:
                leg_contract = ib.qualifyContracts(
                    Contract(conId=leg.conId, exchange=leg.exchange)
                )[0]
                combo_legs_data.append(
                    {
                        "symbol": leg_contract.symbol,
                        "sec_type": leg_contract.secType,
                        "expiry": getattr(
                            leg_contract, "lastTradeDateOrContractMonth", None
                        ),
                        "strike": getattr(leg_contract, "strike", None),
                        "right": getattr(leg_contract, "right", None),
                        "ratio": leg.ratio,
                        "action": leg.action,
                        "exchange": leg.exchange,
                    }
                )

        open_orders.append(
            OpenOrder(
                order_id=o.orderId,
                perm_id=o.permId,
                symbol=c.symbol,
                sec_type=c.secType,
                currency=c.currency,
                expiry=getattr(c, "lastTradeDateOrContractMonth", None),
                strike=getattr(c, "strike", None),
                right=getattr(c, "right", None),
                combo_legs=combo_legs_data if combo_legs_data else None,
                side=o.action,
                total_qty=o.totalQuantity,
                lmt_price=o.lmtPrice if o.orderType in {"LMT", "LIT", "REL"} else None,
                aux_price=o.auxPrice if hasattr(o, "auxPrice") else None,
                tif=o.tif,
                order_type=o.orderType,
                algo_strategy=o.algoStrategy,
                status=status.status if status else "Unknown",
                filled=status.filled if status else 0,
                remaining=status.remaining if status else o.totalQuantity,
                account=o.account,
                order_ref=o.orderRef,
            )
        )

    ib.disconnect()
    return trades, open_orders


# Helper for PDF tables: size columns based on content length
def _calc_table_col_widths(
    data: list[list],
    page_width: float,
    fixed_idx: int | None = None,
    fixed_pct: float = 0.40,
) -> list[float]:
    """
    Return a list of column widths (in points) that add up to page_width.

    * data       — table data including header row (list of rows)
    * page_width — available width in the PDF page (points)
    * fixed_idx  — if not None, reserve `fixed_pct` of page_width for this column
    * fixed_pct  — fraction of page_width for the fixed column (default 40 %)
    """
    ncols = len(data[0])
    # maximum visible string length per column (header + cells)
    max_lens = [max(len(str(row[i])) for row in data) for i in range(ncols)]

    if fixed_idx is not None:
        fixed_w = page_width * fixed_pct
        flexible_w = page_width - fixed_w
        total_len = sum(max_lens[i] for i in range(ncols) if i != fixed_idx) or 1
        col_widths = [
            fixed_w if i == fixed_idx else flexible_w * max_lens[i] / total_len
            for i in range(ncols)
        ]
    else:
        total_len = sum(max_lens) or 1
        col_widths = [page_width * l / total_len for l in max_lens]

    return col_widths


# Save PDF report with trades and open orders
def save_pdf(
    trades: Iterable[Trade],
    open_orders: Iterable[OpenOrder],
    start: date,
    end: date,
    out_path: Path,
) -> Optional[Path]:
    trades = list(trades)
    open_orders = list(open_orders)
    if not trades and not open_orders:
        return None

    pdf_path = Path(out_path)

    df_trades = pd.DataFrame([t.__dict__ for t in trades])
    df_open = pd.DataFrame([o.__dict__ for o in open_orders])

    elements = []
    styles = getSampleStyleSheet()
    hdr_style = styles["Heading2"]
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=landscape(letter),
        rightMargin=18,
        leftMargin=18,
        topMargin=18,
        bottomMargin=18,
    )
    # ---- compute usable page width and prettify numeric columns ----
    page_width = landscape(letter)[0] - doc.leftMargin - doc.rightMargin

    df_trades_fmt = df_trades.copy()
    if not df_trades_fmt.empty:
        # -- strip internal identifier fields; they clutter the PDF --
        drop_trade_cols = ["exec_id", "perm_id", "order_id", "model_code", "order_ref"]
        df_trades_fmt.drop(
            columns=[c for c in drop_trade_cols if c in df_trades_fmt.columns],
            inplace=True,
            errors="ignore",
        )
        num_cols = df_trades_fmt.select_dtypes(include=[float, int]).columns
        for col in num_cols:
            df_trades_fmt[col] = df_trades_fmt[col].map(
                lambda x: f"{x:,.3f}" if isinstance(x, (float, int)) else x
            )
        if "combo_legs" in df_trades_fmt.columns:
            df_trades_fmt["combo_legs"] = df_trades_fmt["combo_legs"].apply(
                lambda x: (
                    "\n".join(
                        [
                            f"{leg['ratio']}x {leg['action']} {leg['symbol']} ({leg['sec_type']}) "
                            f"Exp: {leg['expiry'] or 'N/A'}, Strike: {leg['strike'] or 'N/A'}, Right: {leg['right'] or 'N/A'}"
                            for leg in x
                        ]
                    )
                    if x
                    else None
                )
            )

    df_open_fmt = df_open.copy()
    if not df_open_fmt.empty:
        # -- strip ID-style columns from open orders as well --
        drop_open_cols = ["order_id", "perm_id"]
        df_open_fmt.drop(
            columns=[c for c in drop_open_cols if c in df_open_fmt.columns],
            inplace=True,
            errors="ignore",
        )
        num_cols_open = df_open_fmt.select_dtypes(include=[float, int]).columns
        for col in num_cols_open:
            df_open_fmt[col] = df_open_fmt[col].map(
                lambda x: f"{x:,.3f}" if isinstance(x, (float, int)) else x
            )
        if "combo_legs" in df_open_fmt.columns:
            df_open_fmt["combo_legs"] = df_open_fmt["combo_legs"].apply(
                lambda x: (
                    "\n".join(
                        [
                            f"{leg['ratio']}x {leg['action']} {leg['symbol']} ({leg['sec_type']}) "
                            f"Exp: {leg['expiry'] or 'N/A'}, Strike: {leg['strike'] or 'N/A'}, Right: {leg['right'] or 'N/A'}"
                            for leg in x
                        ]
                    )
                    if x
                    else None
                )
            )

    # ---- TRADES TABLE (consolidated for readability) ----
    if not df_trades_fmt.empty:
        elements.append(Paragraph("Trades Executed", hdr_style))
        elements.append(Spacer(1, 6))

        trade_cols = [
            "datetime",
            "symbol",
            "side",
            "qty",
            "price",
            "avg_price",
            "realized_pnl",
            "commission",
            "currency",
            "expiry",
            "strike",
            "right",
            "combo_legs",
        ]
        trade_cols = [c for c in trade_cols if c in df_trades_fmt.columns]

        data = [trade_cols] + df_trades_fmt[trade_cols].values.tolist()

        combo_idx = (
            trade_cols.index("combo_legs") if "combo_legs" in trade_cols else None
        )
        col_widths = _calc_table_col_widths(data, page_width, fixed_idx=combo_idx)

        tbl = Table(data, repeatRows=1, colWidths=col_widths, hAlign="LEFT")
        tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.darkblue),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                    ("ALIGN", (0, 1), (-1, -1), "RIGHT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 9),
                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.whitesmoke, colors.lightgrey],
                    ),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.black),
                ]
            )
        )
        elements.append(tbl)
        elements.append(PageBreak())

    # ---- OPEN ORDERS TABLE (consolidated) ----
    if not df_open_fmt.empty:
        elements.append(Paragraph("Open Orders", hdr_style))
        elements.append(Spacer(1, 6))

        open_cols = [
            "symbol",
            "side",
            "total_qty",
            "status",
            "filled",
            "remaining",
            "lmt_price",
            "aux_price",
            "expiry",
            "strike",
            "right",
            "combo_legs",
        ]
        open_cols = [c for c in open_cols if c in df_open_fmt.columns]

        data = [open_cols] + df_open_fmt[open_cols].values.tolist()

        combo_idx = open_cols.index("combo_legs") if "combo_legs" in open_cols else None
        col_widths = _calc_table_col_widths(data, page_width, fixed_idx=combo_idx)

        tbl = Table(data, repeatRows=1, colWidths=col_widths, hAlign="LEFT")
        tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.darkgreen),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                    ("ALIGN", (0, 1), (-1, -1), "RIGHT"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 9),
                    ("FONTSIZE", (0, 1), (-1, -1), 8),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.whitesmoke, colors.lightgrey],
                    ),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.black),
                ]
            )
        )
        elements.append(tbl)

    doc.build(elements)
    return pdf_path


def run(
    fmt: str = "csv",
    show_actions: bool = False,
    include_open: bool = True,
    return_df: bool = False,
    save_combos: bool = True,
) -> pd.DataFrame | None:
    """Generate trades report and export in desired format.

    When invoked from the menu ("Executions / open orders"), this also saves
    a `trades_combos.csv` file by default, mirroring the CLI behavior.
    """
    trades = _load_trades()
    if trades is None:
        return None

    df_exec = trades.copy()
    open_df = None
    if include_open:
        open_df = _load_open_orders()
        df = pd.concat([df_exec, open_df], ignore_index=True, sort=False)
    else:
        df = df_exec

    if df.empty:
        print("⚠️ No trades found for the specified date range; no report generated.")
        return None
    if show_actions:
        df["Action"] = df.apply(
            lambda r: r["Action"] if r.get("Action") == "Open" else _classify(r),
            axis=1,
        )
    # Determine earliest execution and load a prior snapshot strictly older when possible
    try:
        earliest_exec_ts = _get_earliest_exec_ts(df_exec)
    except Exception:
        earliest_exec_ts = None
    outdir = Path(config_core.settings.output_dir)
    prev_positions_df, _prior_path = _ensure_prev_positions_quiet(earliest_exec_ts, outdir)
    # Prefer vectorized streaming intent; falls back row-wise when needed
    df["position_effect"] = _compute_streaming_effect(df, prev_positions_df)

    from portfolio_exporter.core.io import save

    # Timestamped filename for easier tracking and to avoid overwrites
    date_tag = datetime.now(ZoneInfo(settings.timezone)).strftime("%Y%m%d_%H%M")
    path = save(df, f"trades_report_{date_tag}", fmt, settings.output_dir)
    print(f"✅ Trades report exported → {path}")

    # Also detect and save combos unless disabled
    if save_combos:
        try:
            combos_df = _detect_and_enrich_trades_combos(df_exec, open_df, prev_positions_df)
            path_combos = _save_trades_combos(combos_df, fmt="csv")
            print(f"✅ Trades combos exported → {path_combos}")
        except Exception as exc:  # pragma: no cover - defensive
            print(f"⚠️ Trades combos export skipped: {exc}")

    if return_df:
        return df
    return None


# ───────────────────────── combos from trades/open orders ─────────────────────────
def _standardize_cols(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    d = df.copy()
    # common aliases
    rename = {}
    for a, b in (
        ("sec_type", "secType"),
        ("underlying", "symbol"),
        ("permId", "perm_id"),
        ("orderId", "order_id"),
    ):
        if a in d.columns and b not in d.columns:
            rename[a] = b
    if rename:
        d = d.rename(columns=rename)

    # unify side text
    def _norm_side(x: object) -> str:
        s = str(x).strip().upper()
        if s in {"BOT", "BUY"}:
            return "BUY"
        if s in {"SLD", "SELL"}:
            return "SELL"
        return s

    for c in ("Side", "side"):
        if c in d.columns:
            d[c] = d[c].apply(_norm_side)

    # datetime parsing
    for c in ("datetime", "timestamp", "time"):
        if c in d.columns:
            try:
                d[c] = pd.to_datetime(d[c], errors="coerce")
            except Exception:
                pass
            if c != "datetime" and "datetime" not in d.columns:
                d["datetime"] = d[c]
            break

    # numeric coercions
    for c in ("qty", "Qty", "total_qty"):
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    for c in ("strike", "price", "lmt_price", "aux_price", "multiplier"):
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")

    # right normalization
    if "right" in d.columns:
        d["right"] = d["right"].astype(str).str.upper().map({"CALL": "C", "PUT": "P", "C": "C", "P": "P"}).fillna("")

    # expiry pass-through
    for c in ("expiry", "lastTradeDateOrContractMonth"):
        if c in d.columns and "expiry" not in d.columns:
            d["expiry"] = d[c]
            break

    # secType pass-through
    for c in ("secType", "sec_type"):
        if c in d.columns and "secType" not in d.columns:
            d["secType"] = d[c]
            break

    # conId pass-through
    for c in ("conId", "conid"):
        if c in d.columns and "conId" not in d.columns:
            d["conId"] = d[c]
            break
    if "conId" in d.columns:
        try:
            d["conId"] = pd.to_numeric(d["conId"], errors="coerce").astype("Int64")
        except Exception:
            pass

    return d


def _build_positions_like_df(execs: pd.DataFrame, opens: pd.DataFrame | None = None) -> pd.DataFrame:
    e = _standardize_cols(execs)
    o = _standardize_cols(opens) if isinstance(opens, pd.DataFrame) else pd.DataFrame()
    frames = [x for x in (e, o) if x is not None and not x.empty]
    if not frames:
        return pd.DataFrame(columns=["underlying", "expiry", "right", "strike", "qty", "secType", "conId", "multiplier", "price", "order_id", "perm_id", "datetime"])
    df = pd.concat(frames, ignore_index=True, sort=False)

    # pick qty, side, price
    qty = (
        df["qty"]
        if "qty" in df.columns
        else df["Qty"] if "Qty" in df.columns
        else df["total_qty"] if "total_qty" in df.columns
        else pd.Series([np.nan] * len(df))
    )
    side = df["Side"] if "Side" in df.columns else df["side"] if "side" in df.columns else pd.Series([""] * len(df))
    # signed qty: BUY +, SELL -
    sign = side.apply(lambda s: 1 if str(s).upper() == "BUY" else (-1 if str(s).upper() == "SELL" else 1))
    qty_signed = pd.to_numeric(qty, errors="coerce").fillna(0).astype(float) * sign
    price = (
        df["price"]
        if "price" in df.columns
        else df["lmt_price"] if "lmt_price" in df.columns
        else pd.Series([np.nan] * len(df))
    )
    # multiplier default per secType
    mult = df.get("multiplier")
    if mult is None or mult.isna().all():
        mult = df.get("secType").map({"OPT": 100, "FOP": 100, "STK": 1, "ETF": 1}).fillna(100)

    out = pd.DataFrame(
        {
            "underlying": df.get("symbol"),
            "expiry": df.get("expiry", ""),
            "right": df.get("right", ""),
            "strike": df.get("strike", np.nan),
            "qty": qty_signed,
            "secType": df.get("secType"),
            "conId": df.get("conId"),
            "multiplier": mult,
            "price": price,
            "order_id": df.get("order_id"),
            "perm_id": df.get("perm_id"),
            "datetime": df.get("datetime"),
            # carry-through fields useful for intent classification
            "Liquidation": df.get("Liquidation"),
            "lastLiquidity": df.get("lastLiquidity"),
            "OrderRef": df.get("OrderRef"),
            "Action": df.get("Action"),
            "openClose": df.get("openClose"),
        }
    )

    # Expand combo legs from BAG rows when available so combo structures have strikes/rights
    try:
        if "secType" in df.columns and "combo_legs" in df.columns:
            import ast
            leg_rows = []
            for _, r in df[df["secType"] == "BAG"].iterrows():
                legs_val = r.get("combo_legs")
                if legs_val is None or (isinstance(legs_val, float) and np.isnan(legs_val)):
                    continue
                seq = None
                if isinstance(legs_val, str):
                    s = legs_val.strip()
                    if s.startswith("[") and s.endswith("]"):
                        try:
                            seq = ast.literal_eval(s)
                        except Exception:
                            seq = None
                elif isinstance(legs_val, (list, tuple)):
                    seq = legs_val
                if not isinstance(seq, (list, tuple)):
                    continue
                pkg_qty = r.get("qty", 1)
                try:
                    pkg_qty = float(pkg_qty)
                except Exception:
                    pkg_qty = 1.0
                for ent in seq:
                    if not isinstance(ent, dict):
                        continue
                    # Derive signed leg qty from leg action and package qty
                    action = str(ent.get("action", "")).upper()
                    ratio = ent.get("ratio", 1)
                    try:
                        ratio = float(ratio)
                    except Exception:
                        ratio = 1.0
                    signed_qty = ratio * pkg_qty * (1 if action == "BUY" else -1)
                    # Build a leg-like row
                    leg_rows.append(
                        {
                            "underlying": ent.get("symbol", r.get("symbol")),
                            "expiry": ent.get("expiry", r.get("expiry")),
                            "right": ent.get("right", ""),
                            "strike": ent.get("strike", np.nan),
                            "qty": signed_qty,
                            "secType": ent.get("sec_type", "OPT"),
                            "conId": np.nan,
                            "multiplier": 100,
                            "price": np.nan,
                            "order_id": r.get("order_id"),
                            "perm_id": r.get("perm_id"),
                            "datetime": r.get("datetime"),
                        }
                    )
            if leg_rows:
                legs_df = pd.DataFrame(leg_rows)
                # Normalize numeric types and rights
                legs_df["strike"] = pd.to_numeric(legs_df["strike"], errors="coerce")
                legs_df["qty"] = pd.to_numeric(legs_df["qty"], errors="coerce")
                legs_df["multiplier"] = pd.to_numeric(legs_df["multiplier"], errors="coerce").fillna(100).astype(int)
                legs_df["right"] = legs_df["right"].astype(str).str.upper().replace({"CALL": "C", "PUT": "P", "NAN": ""})
                legs_df.loc[~legs_df["right"].isin(["C", "P"]) , "right"] = ""
                # Prefer per-leg execution rows when present; skip BAG-expanded
                # legs that duplicate an existing per-leg (same underlying/expiry/right/strike and side).
                def _side_from_qty(q):
                    try:
                        return "long" if float(q) > 0 else "short"
                    except Exception:
                        return "long"
                # Ensure required columns exist on 'out'
                if "underlying" not in out.columns and "symbol" in out.columns:
                    out["underlying"] = out["symbol"]
                for col in ("expiry", "right", "strike", "qty"):
                    if col not in out.columns:
                        out[col] = pd.NA
                out_keys = set()
                if not out.empty:
                    tmp = out.copy()
                    tmp["strike"] = pd.to_numeric(tmp["strike"], errors="coerce")
                    tmp_key = tmp.apply(lambda r: (
                        str(r.get("underlying", "")),
                        str(r.get("expiry", "")),
                        str(r.get("right", "")).upper(),
                        float(r.get("strike")) if pd.notna(r.get("strike")) else float("nan"),
                        _side_from_qty(r.get("qty"))
                    ), axis=1)
                    out_keys = set(tmp_key.tolist())

                def _key_row(r):
                    return (
                        str(r.get("underlying", "")),
                        str(r.get("expiry", "")),
                        str(r.get("right", "")).upper(),
                        float(r.get("strike")) if pd.notna(r.get("strike")) else float("nan"),
                        _side_from_qty(r.get("qty"))
                    )
                legs_df = legs_df[~legs_df.apply(_key_row, axis=1).isin(out_keys)].copy()
                # Prefer leg rows for option-like records and drop BAG placeholders
                out = pd.concat([out[out.get("secType") != "BAG"], legs_df], ignore_index=True, sort=False)
    except Exception:
        # Non-fatal; continue with whatever we have
        pass
    # type coercions
    out["strike"] = pd.to_numeric(out["strike"], errors="coerce")
    out["qty"] = pd.to_numeric(out["qty"], errors="coerce")
    try:
        out["conId"] = pd.to_numeric(out["conId"], errors="coerce").astype("Int64")
    except Exception:
        pass
    # Synthesize conId for rows missing it so that combo legs (which rely on conId) can map back
    try:
        import hashlib as _hl
        def _synth(row):
            try:
                val = row.get("conId")
                if pd.notna(val):
                    return int(val)
            except Exception:
                pass
            key = f"{row.get('underlying','')}|{row.get('expiry','')}|{row.get('right','')}|{row.get('strike','')}"
            v = int.from_bytes(_hl.sha1(str(key).encode()).digest()[:4], "big")
            return -int(v)
        out["conId"] = out.apply(_synth, axis=1).astype("Int64")
    except Exception:
        pass
    try:
        out["multiplier"] = pd.to_numeric(out["multiplier"], errors="coerce").fillna(100).astype(int)
    except Exception:
        out["multiplier"] = 100
    # normalize right
    if "right" in out.columns:
        out["right"] = out["right"].astype(str).str.upper().replace({"CALL": "C", "PUT": "P", "NAN": ""})
        out.loc[~out["right"].isin(["C", "P"]) , "right"] = ""
    return out


def _cluster_executions(execs: pd.DataFrame, window_sec: int = 60) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cluster executions by ``perm_id`` then by ``(underlying, side, window)``.

    Parameters
    ----------
    execs:
        Raw executions DataFrame.
    window_sec:
        Sliding time window in seconds for side-aware clustering when ``perm_id``
        does not form multi-execution groups.

    Returns
    -------
    Tuple[pd.DataFrame, pd.DataFrame]
        ``(clusters, debug_rows)`` where ``clusters`` aggregates per-cluster
        stats and ``debug_rows`` includes the original executions with a
        ``cluster_id`` column.
    """
    if execs is None or execs.empty:
        return pd.DataFrame(), pd.DataFrame()

    df = _standardize_cols(execs)
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    df = df.copy()
    # Normalize core fields
    df["underlying"] = df.get("symbol")
    side = df.get("Side") if "Side" in df.columns else df.get("side")
    df["side"] = side.astype(str).str.upper().replace({"BOT": "BUY", "SLD": "SELL"})
    df["side_sign"] = df["side"].map({"BUY": 1, "SELL": -1}).fillna(0)
    df["qty"] = pd.to_numeric(df.get("qty", df.get("Qty")), errors="coerce").fillna(0).astype(float)
    df["price"] = pd.to_numeric(df.get("price"), errors="coerce").fillna(0).astype(float)
    df["datetime"] = pd.to_datetime(df.get("datetime"), errors="coerce")
    df["multiplier"] = pd.to_numeric(df.get("multiplier"), errors="coerce")
    # safe secType mapping when column is missing
    sec = df.get("secType")
    sec_map = sec.map({"OPT": 100, "FOP": 50}) if sec is not None else pd.Series([None] * len(df))
    df["multiplier"] = df["multiplier"].fillna(sec_map).fillna(1)
    # Optional commission column for net P&L computation
    if "commission" in df.columns:
        try:
            df["commission"] = pd.to_numeric(df.get("commission"), errors="coerce").fillna(0.0)
        except Exception:
            df["commission"] = 0.0
    df["perm_id"] = pd.to_numeric(df.get("perm_id"), errors="coerce").astype("Int64")

    df = df.sort_values("datetime").reset_index(drop=True)
    df["cluster_id"] = pd.NA

    cid = 0

    # Cluster by perm_id where there are multiple executions
    perm_counts = df["perm_id"].value_counts(dropna=True)
    for pid, count in perm_counts.items():
        if pd.isna(pid) or int(pid) <= 0 or count < 2:
            continue
        cid += 1
        mask = df["perm_id"] == pid
        df.loc[mask, "cluster_id"] = cid

    # Remaining rows: cluster by underlying+side within window
    remaining = df[df["cluster_id"].isna()].copy()
    for (_u, _s), g in remaining.groupby(["underlying", "side"], dropna=False):
        g = g.sort_values("datetime")
        last_dt = None
        for idx, row in g.iterrows():
            if last_dt is None or pd.isna(row["datetime"]) or (
                row["datetime"] - last_dt
            ).total_seconds() > window_sec:
                cid += 1
            df.at[idx, "cluster_id"] = cid
            last_dt = row["datetime"]

    df["cluster_id"] = pd.to_numeric(df["cluster_id"], errors="coerce").astype(int)
    df["pnl_leg"] = df["side_sign"] * df["price"] * df["qty"] * df["multiplier"]

    # Aggregate per cluster
    def _join_perm(vals: pd.Series) -> str:
        uniq = sorted({str(int(v)) for v in vals.dropna().astype(int) if int(v) > 0})
        return "/".join(uniq)

    clusters = (
        df.groupby("cluster_id")
        .agg(
            perm_ids=("perm_id", _join_perm),
            underlying=("underlying", "first"),
            start=("datetime", "min"),
            end=("datetime", "max"),
            pnl=("pnl_leg", "sum"),
            commission=("commission", "sum") if "commission" in df.columns else ("pnl_leg", "sum"),
            legs_n=("exec_id", "count"),
        )
        .reset_index()
    )
    try:
        if "commission" in clusters.columns:
            clusters["pnl_net"] = pd.to_numeric(clusters.get("pnl"), errors="coerce").fillna(0.0) - pd.to_numeric(clusters.get("commission"), errors="coerce").fillna(0.0)
    except Exception:
        pass

    structures: dict[int, str] = {}
    for cid, g in df.groupby("cluster_id"):
        try:
            pos = _build_positions_like_df(g, None)
            detected = combo_core.detect_from_positions(pos)
            if isinstance(detected, pd.DataFrame) and not detected.empty:
                structures[cid] = str(detected.iloc[0].get("structure", "synthetic"))
            else:
                structures[cid] = "synthetic"
        except Exception:
            structures[cid] = "synthetic"
    clusters["structure"] = clusters["cluster_id"].map(structures).fillna("synthetic")

    return clusters, df


def _detect_and_enrich_trades_combos(
    execs_df: pd.DataFrame,
    opens_df: pd.DataFrame | None = None,
    prev_positions_df: pd.DataFrame | None = None,
    debug_rows: list | None = None,
    clusters_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    # Build positions-like df
    pos_like = _build_positions_like_df(execs_df, opens_df)
    if pos_like is None or pos_like.empty:
        return pd.DataFrame(columns=[
            "underlying","expiry","structure","structure_label","type","legs","legs_n","width","strikes","call_strikes","put_strikes","call_count","put_count","has_stock_leg","when","order_ids","net_qty","net_credit_debit","position_effect",
        ])

    # Group by underlying (simple clustering per Phase 1)
    combos_rows: list[pd.DataFrame] = []
    meta_rows: list[dict] = []
    for u, g in pos_like.groupby("underlying"):
        # Detect combos for this underlying
        detected = combo_core.detect_from_positions(g)
        if detected is None or detected.empty:
            continue
        detected = detected.copy()
        # attach per-underlying meta
        when_val = None
        try:
            when_val = pd.to_datetime(g.get("datetime"), errors="coerce").min()
        except Exception:
            when_val = pd.NaT
        order_ids = []
        for c in ("order_id", "perm_id"):
            if c in g.columns:
                order_ids.extend(sorted(set([str(x) for x in g[c].dropna().tolist()])))
        # net qty and net credit/debit
        net_qty = float(pd.to_numeric(g.get("qty"), errors="coerce").fillna(0).sum())
        try:
            ncd = (-pd.to_numeric(g.get("price"), errors="coerce") * pd.to_numeric(g.get("qty"), errors="coerce") * pd.to_numeric(g.get("multiplier"), errors="coerce")).sum()
            net_cd = float(ncd) if pd.notna(ncd) else np.nan
        except Exception:
            net_cd = np.nan

        detected["when"] = when_val
        detected["order_ids"] = ",".join(sorted(set(order_ids))) if order_ids else ""
        detected["net_qty"] = net_qty
        detected["net_credit_debit"] = net_cd
        combos_rows.append(detected)

    if not combos_rows:
        combos_df = pd.DataFrame()
    else:
        combos_df = pd.concat(combos_rows, ignore_index=True, sort=False)

    # Attach realized P&L per combo by intersecting order/perm IDs with clusters
    try:
        if isinstance(combos_df, pd.DataFrame) and not combos_df.empty and isinstance(clusters_df, pd.DataFrame) and not clusters_df.empty:
            # Build map: cluster index -> set of perm_ids and pnl
            def _to_perm_set(val: object) -> set[int]:
                s = set()
                for tok in str(val).replace("/", ",").split(","):
                    tok = tok.strip()
                    if not tok:
                        continue
                    try:
                        s.add(int(tok))
                    except Exception:
                        pass
                return s

            cl_perm = clusters_df.get("perm_ids") if "perm_ids" in clusters_df.columns else None
            cl_map = []
            if cl_perm is not None:
                cl_map = [
                    (
                        _to_perm_set(v),
                        float(p) if pd.notna(p) else 0.0,
                        float(n) if pd.notna(n) else 0.0,
                    )
                    for v, p, n in zip(
                        clusters_df["perm_ids"],
                        clusters_df.get("pnl", 0.0),
                        clusters_df.get("pnl_net", 0.0)
                        if "pnl_net" in clusters_df.columns
                        else clusters_df.get("pnl", 0.0),
                    )
                ]
            pnls: list[float] = []
            pnls_net: list[float] = []
            for _, row in combos_df.iterrows():
                ids = _to_perm_set(row.get("order_ids", ""))
                total = 0.0
                total_net = 0.0
                if ids:
                    for perm_set, pnl, pnl_n in cl_map:
                        if perm_set and ids.intersection(perm_set):
                            total += float(pnl)
                            total_net += float(pnl_n)
                pnls.append(total)
                pnls_net.append(total_net)
            combos_df["pnl"] = pnls
            combos_df["pnl_net"] = pnls_net
    except Exception:
        pass

    # Enrichment – prefer positions mapping
    if _enrich_combo_strikes_greeks is not None:
        try:
            combos_df = _enrich_combo_strikes_greeks(combos_df, positions_df=pos_like)
        except Exception:
            pass
    else:
        # Minimal fallback enrichment if portfolio_greeks helper is unavailable
        combos_df = _enrich_combo_strikes_fallback(combos_df, pos_like)

    # Normalize legs to a JSON list string and recompute legs_n
    try:
        def _to_json_list(v):
            if isinstance(v, list):
                return json.dumps(v)
            if isinstance(v, str) and v.strip().startswith("["):
                return v
            return json.dumps([])
        if "legs" in combos_df.columns:
            combos_df["legs"] = combos_df["legs"].apply(_to_json_list)
            # legs_n must reflect parsed length
            def _len_json(s):
                try:
                    return len(json.loads(s)) if isinstance(s, str) else 0
                except Exception:
                    return 0
            combos_df["legs_n"] = combos_df["legs"].apply(_len_json).astype("Int64")
    except Exception:
        pass

    # De-duplicate combos by normalized leg set per (underlying, expiry, structure, type)
    try:
        import ast
        def _legs_sig(s: str) -> tuple:
            try:
                val = ast.literal_eval(s) if isinstance(s, str) else (s or [])
            except Exception:
                val = []
            # Keep only integers (conIds), sort for stable signature
            ids = []
            for x in (val or []):
                try:
                    if isinstance(x, (int,)) or (isinstance(x, str) and str(x).lstrip("-").isdigit()):
                        ids.append(int(x))
                except Exception:
                    continue
            return tuple(sorted(ids))
        key_cols = [c for c in ["underlying", "expiry", "structure", "type"] if c in combos_df.columns]
        if key_cols and "legs" in combos_df.columns:
            tmp = combos_df.copy()
            tmp["__legs_sig"] = tmp["legs"].apply(_legs_sig)
            tmp["__dedupe_key"] = tmp[key_cols].astype(str).agg("|".join, axis=1) + "#" + tmp["__legs_sig"].astype(str)
            tmp = tmp.drop_duplicates(subset=["__dedupe_key"], keep="first").drop(columns=["__dedupe_key", "__legs_sig"])  # type: ignore
            combos_df = tmp
    except Exception:
        pass

    # Annotate position_effect for combos using leg-level execution intent
    try:
        # reconstruct prior positions if our snapshot represents 'after' state
        prior_df = _reconstruct_prior_positions(prev_positions_df, execs_df)
        combos_df = _annotate_combos_effect(combos_df, pos_like, prior_df, debug_rows)
    except Exception:
        pass
    # Ensure a defensive default column
    try:
        if "position_effect" not in combos_df.columns:
            combos_df["position_effect"] = "Unknown"
    except Exception:
        pass
    return combos_df


def _reconstruct_prior_positions(current_positions: pd.DataFrame | None, execs_df: pd.DataFrame | None) -> pd.DataFrame | None:
    """Rebuild a 'before trades' positions view from current positions and executions.

    before = after - delta, where delta is the signed quantity from executions.
    Returns a normalized positions-like DataFrame (columns at least underlying, expiry, right, strike, qty).
    """
    if current_positions is None or not isinstance(current_positions, pd.DataFrame) or current_positions.empty:
        return current_positions
    try:
        # Normalize current positions
        after = combo_core._normalize_positions_df(current_positions)
        # Build delta from executions
        delta_src = _build_positions_like_df(execs_df, None) if isinstance(execs_df, pd.DataFrame) else pd.DataFrame()
        if delta_src is None:
            delta_src = pd.DataFrame()
        try:
            delta = combo_core._normalize_positions_df(delta_src)
        except Exception:
            delta = delta_src.copy()
        # Aggregate
        key_cols = ["underlying","expiry","right","strike","secType"]
        def _agg(df: pd.DataFrame) -> pd.DataFrame:
            if df is None or df.empty:
                return pd.DataFrame(columns=key_cols + ["qty"]) 
            d = df.copy()
            if "qty" not in d.columns:
                d["qty"] = 0.0
            try:
                d["qty"] = pd.to_numeric(d["qty"], errors="coerce").fillna(0.0)
            except Exception:
                d["qty"] = 0.0
            g = d.groupby(key_cols, dropna=False)["qty"].sum().reset_index()
            return g
        A = _agg(after)
        D = _agg(delta)
        # Merge and compute prior = after - delta
        merged = pd.merge(A, D, on=key_cols, how="left", suffixes=("_after","_delta"))
        merged["qty_delta"] = pd.to_numeric(merged.get("qty_delta"), errors="coerce").fillna(0.0)
        merged["qty_before"] = pd.to_numeric(merged.get("qty_after"), errors="coerce").fillna(0.0) - merged["qty_delta"]
        prior = merged[key_cols + ["qty_before"]].rename(columns={"qty_before":"qty"})
        # keep only non-zero
        try:
            prior = prior[prior["qty"].abs() > 0]
        except Exception:
            pass
        return prior
    except Exception:
        return current_positions


def _annotate_combos_effect(
    combos_df: pd.DataFrame,
    pos_like: pd.DataFrame,
    prev_positions: pd.DataFrame | None = None,
    debug_rows: list | None = None,
) -> pd.DataFrame:
    """Derive position_effect for combos by reconciling legs to prior positions.

    Uses the same normalization and hashing as the combo detector so leg IDs
    match across frames. Falls back to attribute-based hashing when prior
    positions carry real conIds.
    """
    df = combos_df.copy() if isinstance(combos_df, pd.DataFrame) else pd.DataFrame()
    if df.empty or "legs" not in df.columns or pos_like is None or pos_like.empty:
        return df

    import ast, hashlib

    # Normalize current trade legs frame to get (conId -> attrs)
    try:
        norm_tx = combo_core._normalize_positions_df(pos_like)
    except Exception:
        norm_tx = pos_like.copy()
    for col in ("conId", "strike"):
        if col in norm_tx.columns:
            try:
                norm_tx[col] = pd.to_numeric(norm_tx[col], errors="coerce")
            except Exception:
                pass
    id_to_exp = {}
    id_to_attr: dict[int, dict] = {}
    try:
        for _, r in norm_tx.iterrows():
            cid = r.get("conId")
            if pd.notna(cid):
                id_to_exp[int(cid)] = str(r.get("expiry") or "")
                id_to_attr[int(cid)] = {
                    "underlying": (str(r.get("underlying") or r.get("symbol") or "")).upper(),
                    "expiry": _normalize_expiry(r.get("expiry")),
                    "right": (str(r.get("right") or "")).upper(),
                    "strike": (float(r.get("strike")) if pd.notna(r.get("strike")) else float("nan")),
                }
    except Exception:
        pass

    # Normalize previous positions; compute a synthetic hash ID matching detector
    prev_norm = pd.DataFrame()
    if prev_positions is not None and isinstance(prev_positions, pd.DataFrame) and not prev_positions.empty:
        try:
            prev_norm = combo_core._normalize_positions_df(prev_positions)
        except Exception:
            prev_norm = prev_positions.copy()
    if not prev_norm.empty:
        # Ensure normalized columns exist
        for c in ("underlying", "expiry", "right", "strike", "qty"):
            if c not in prev_norm.columns:
                prev_norm[c] = pd.NA
        try:
            prev_norm["strike"] = pd.to_numeric(prev_norm["strike"], errors="coerce")
        except Exception:
            pass
        # Normalize for attribute matching
        prev_norm["__sym"] = prev_norm.get("underlying").astype(str).str.upper()
        prev_norm["__right"] = prev_norm.get("right").astype(str).str.upper()
        prev_norm["__exp"] = prev_norm.get("expiry").apply(_normalize_expiry)
        def _round_strike(x):
            try:
                return float(f"{float(x):.2f}")
            except Exception:
                return float("nan")
        prev_norm["__k2"] = prev_norm.get("strike").apply(_round_strike)
        def _synth_id(row: pd.Series) -> int:
            key = f"{row.get('underlying','')}|{row.get('expiry','')}|{row.get('right','')}|{row.get('strike')}"
            v = int.from_bytes(hashlib.sha1(str(key).encode()).digest()[:4], 'big')
            return -int(v)
        try:
            prev_norm["__synth_id"] = prev_norm.apply(_synth_id, axis=1).astype("Int64")
        except Exception:
            prev_norm["__synth_id"] = pd.NA
        try:
            prev_norm["qty"] = pd.to_numeric(prev_norm["qty"], errors="coerce").fillna(0.0)
        except Exception:
            prev_norm["qty"] = 0.0
        prior_ids = set(int(x) for x in prev_norm.loc[prev_norm["qty"] != 0, "__synth_id"].dropna().tolist())
        prior_id_to_exp: dict[int, str] = {}
        prior_id_to_qty: dict[int, float] = {}
        try:
            for _, r in prev_norm.iterrows():
                sid = r.get("__synth_id")
                if pd.notna(sid):
                    prior_id_to_exp[int(sid)] = str(r.get("expiry") or "")
                    try:
                        prior_id_to_qty[int(sid)] = float(r.get("qty") or 0.0)
                    except Exception:
                        prior_id_to_qty[int(sid)] = 0.0
        except Exception:
            pass
    else:
        # No prior snapshot available; treat as empty so attribute fallback classifies legs as Open
        prior_ids = set()
        prior_id_to_exp = {}
        prior_id_to_qty = {}
        try:
            import pandas as _pd
            prev_norm = _pd.DataFrame(columns=["__sym","__right","__exp","__k2","qty"])  # empty placeholder
        except Exception:
            prev_norm = None  # type: ignore

    def _parse_legs(val: object) -> list[int]:
        if isinstance(val, list):
            seq = val
        elif isinstance(val, str) and val.strip().startswith("["):
            try:
                seq = ast.literal_eval(val)
            except Exception:
                seq = []
        else:
            seq = []
        out: list[int] = []
        for x in seq or []:
            try:
                if isinstance(x, dict):
                    cid = x.get("conId") or x.get("conid") or x.get("id")
                    if cid is not None:
                        out.append(int(cid))
                elif isinstance(x, (int,)) or (isinstance(x, str) and str(x).lstrip("-").isdigit()):
                    out.append(int(x))
            except Exception:
                continue
        return out

    effects: list[str] = []
    for idx, row in df.iterrows():
        cids = _parse_legs(row.get("legs"))
        open_exp: set[str] = set()
        close_exp: set[str] = set()
        match_id = 0
        match_attr_exact = 0
        match_attr_tol = 0
        openc = 0
        closec = 0
        combo_sig = str(row.get("__dedupe_key") or f"{row.get('underlying','')}|{row.get('expiry','')}|{row.get('structure','')}|{row.get('type','')}")
        for cid in cids:
            # Determine expiry for this leg from current trade context
            exp = id_to_exp.get(cid, prior_id_to_exp.get(cid, ""))
            if cid in prior_ids:
                close_exp.add(exp)
                closec += 1
                match_id += 1
                if debug_rows is not None:
                    attrs = id_to_attr.get(cid, {})
                    debug_rows.append({
                        "combo_sig": combo_sig,
                        "underlying": attrs.get("underlying"),
                        "expiry": _normalize_expiry(attrs.get("expiry")),
                        "right": attrs.get("right"),
                        "strike": attrs.get("strike"),
                        "match_mode": "id",
                        "prior_qty": prior_id_to_qty.get(cid, 0.0),
                        "leg_effect": "Close",
                    })
            else:
                # attribute fallback
                attrs = id_to_attr.get(cid, {})
                # exact first (rounded strike equality)
                sym = (attrs.get("underlying") or "").upper()
                expn = _normalize_expiry(attrs.get("expiry"))
                rgt = (attrs.get("right") or "").upper()
                try:
                    k2 = float(f"{float(attrs.get('strike')):.2f}")
                except Exception:
                    k2 = float("nan")
                exact = prev_norm[(prev_norm["__sym"] == sym) & (prev_norm["__right"] == rgt) & (prev_norm["__exp"] == expn) & (prev_norm["__k2"] == k2)]
                tol = prev_norm[(prev_norm["__sym"] == sym) & (prev_norm["__right"] == rgt) & (prev_norm["__exp"] == expn) & (prev_norm["__k2"].sub(k2).abs() <= 0.05)] if not np.isnan(k2) else prev_norm.iloc[0:0]
                if not exact.empty:
                    close_exp.add(exp)
                    closec += 1
                    match_attr_exact += 1
                    if debug_rows is not None:
                        debug_rows.append({
                            "combo_sig": combo_sig,
                            "underlying": sym,
                            "expiry": expn,
                            "right": rgt,
                            "strike": k2,
                            "match_mode": "attr_exact",
                            "prior_qty": float(exact.get("qty", pd.Series([0.0])).astype(float).sum()),
                            "leg_effect": "Close",
                        })
                elif not tol.empty:
                    close_exp.add(exp)
                    closec += 1
                    match_attr_tol += 1
                    if debug_rows is not None:
                        debug_rows.append({
                            "combo_sig": combo_sig,
                            "underlying": sym,
                            "expiry": expn,
                            "right": rgt,
                            "strike": k2,
                            "match_mode": "attr_tol",
                            "prior_qty": float(tol.get("qty", pd.Series([0.0])).astype(float).sum()),
                            "leg_effect": "Close",
                        })
                else:
                    open_exp.add(exp)
                    openc += 1
                    if debug_rows is not None:
                        debug_rows.append({
                            "combo_sig": combo_sig,
                            "underlying": sym,
                            "expiry": expn,
                            "right": rgt,
                            "strike": k2,
                            "match_mode": "no_match",
                            "prior_qty": 0.0,
                            "leg_effect": "Open",
                        })
        if open_exp and close_exp:
            # If expiries differ across groups → Roll, else Mixed
            effects.append("Roll" if open_exp != close_exp else "Mixed")
        elif open_exp:
            effects.append("Open")
        elif close_exp:
            effects.append("Close")
        else:
            effects.append("Unknown")

        # attach counters for visibility
        try:
            df.loc[idx, "legs_open_count"] = int(openc)
            df.loc[idx, "legs_close_count"] = int(closec)
            df.loc[idx, "legs_match_id_count"] = int(match_id)
            df.loc[idx, "legs_match_attr_exact_count"] = int(match_attr_exact)
            df.loc[idx, "legs_match_attr_tol_count"] = int(match_attr_tol)
        except Exception:
            pass

    df["position_effect"] = effects
    return df


def _save_trades_combos(
    df: pd.DataFrame, fmt: str = "csv", outdir: Path | None = None
) -> Path:
    """Persist combos DataFrame using existing schema."""

    # Deduplicate defensively by legs signature and key identifiers
    out = df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
    try:
        import ast
        def _legs_sig(s: object) -> tuple:
            if isinstance(s, list):
                seq = s
            elif isinstance(s, str) and s.strip().startswith("["):
                try:
                    seq = ast.literal_eval(s)
                except Exception:
                    seq = []
            else:
                seq = []
            ids = []
            for x in (seq or []):
                try:
                    if isinstance(x, (int,)) or (isinstance(x, str) and str(x).lstrip("-").isdigit()):
                        ids.append(int(x))
                except Exception:
                    continue
            return tuple(sorted(ids))
        if not out.empty and "legs" in out.columns:
            key_cols = [c for c in ["underlying","expiry","structure","type"] if c in out.columns]
            out["__legs_sig"] = out["legs"].apply(_legs_sig)
            if key_cols:
                out["__dedupe_key"] = out[key_cols].astype(str).agg("|".join, axis=1) + "#" + out["__legs_sig"].astype(str)
                out = out.drop_duplicates(subset=["__dedupe_key"], keep="first")
            # also drop exact duplicates as an extra guard
            out = out.drop_duplicates()
    except Exception:
        # if anything goes wrong, proceed with original frame
        out = df.copy()

    # Drop debug/helper columns from save output
    out = out.drop(
        columns=["__db_legs_detail", "__strike_source", "__healed_legs"],
        errors="ignore",
    )
    target = outdir or config_core.settings.output_dir
    return io_core.save(out, "trades_combos", fmt, target)


def _enrich_combo_strikes_fallback(combos_df: pd.DataFrame, positions_df: pd.DataFrame | None) -> pd.DataFrame:
    df = combos_df.copy() if isinstance(combos_df, pd.DataFrame) else pd.DataFrame()
    if df.empty:
        for c in ("strikes", "call_strikes", "put_strikes"):
            df[c] = ""
        for c in ("call_count", "put_count"):
            df[c] = 0
        df["has_stock_leg"] = False
        return df

    # Build positions lookup by conId
    if positions_df is None or positions_df.empty:
        pos_lookup = pd.DataFrame(columns=["right", "strike", "secType"]).set_index(pd.Index([], name="conid"))
    else:
        p = positions_df.copy()
        if "conId" in p.columns and "conid" not in p.columns:
            p = p.rename(columns={"conId": "conid"})
        if "conid" not in p.columns:
            p["conid"] = pd.NA
        for c in ("right", "strike", "secType"):
            if c not in p.columns:
                p[c] = pd.NA
        p["conid"] = pd.to_numeric(p["conid"], errors="coerce")
        p = p.dropna(subset=["conid"]).copy()
        p["conid"] = p["conid"].astype(int)
        p["strike"] = pd.to_numeric(p["strike"], errors="coerce")
        pos_lookup = p.set_index("conid")[ ["right", "strike", "secType"] ]

    df = df.copy()
    df["strikes"] = ""
    df["call_strikes"] = ""
    df["put_strikes"] = ""
    df["call_count"] = 0
    df["put_count"] = 0
    df["has_stock_leg"] = False
    df["__strike_source"] = ""

    fmt = lambda x: ("{:.1f}".format(float(x)).rstrip("0").rstrip("."))

    import ast
    res = {k: [] for k in ["strikes","call_strikes","put_strikes","call_count","put_count","has_stock_leg","__strike_source"]}

    def _collect(legs_val):
        leg_ids, leg_dicts = [], []
        def _from_seq(seq):
            for x in seq:
                if isinstance(x, (int,)) or (isinstance(x, str) and str(x).lstrip("-").isdigit()):
                    try:
                        leg_ids.append(int(x))
                    except Exception:
                        pass
                elif isinstance(x, dict):
                    leg_dicts.append(x)
                elif isinstance(x, (list, tuple)) and len(x) >= 2:
                    try:
                        right = str(x[0]).upper()
                    except Exception:
                        right = ""
                    try:
                        strike = float(x[1]) if x[1] is not None else None
                    except Exception:
                        strike = None
                    leg_dicts.append({"right": right if right in ("C","P") else "", "strike": strike, "secType": None})
        if isinstance(legs_val, list):
            _from_seq(legs_val)
        elif isinstance(legs_val, str) and legs_val.strip().startswith("["):
            try:
                parsed = ast.literal_eval(legs_val)
                if isinstance(parsed, (list, tuple)):
                    _from_seq(parsed)
            except Exception:
                pass
        return leg_ids, leg_dicts

    for _, row in df.iterrows():
        leg_ids, leg_dicts = _collect(row.get("legs"))
        call_k, put_k = set(), set()
        call_n = 0
        put_n = 0
        stock_flag = False
        source_tag = ""
        for cid in leg_ids:
            if cid in pos_lookup.index:
                rec = pos_lookup.loc[cid]
                if isinstance(rec, pd.DataFrame):
                    rec = rec.iloc[0]
                r = (str(rec.get("right")) if pd.notna(rec.get("right")) else "").upper()
                k = rec.get("strike")
                st = str(rec.get("secType")) if pd.notna(rec.get("secType")) else ""
                if r == "C":
                    call_n += 1
                    if pd.notna(k):
                        try:
                            call_k.add(float(k))
                        except Exception:
                            pass
                elif r == "P":
                    put_n += 1
                    if pd.notna(k):
                        try:
                            put_k.add(float(k))
                        except Exception:
                            pass
                if st == "STK" or r == "":
                    stock_flag = True
                source_tag = source_tag or "pos"
        # Also include dict-style legs if present (already normalized above)
        for ent in leg_dicts:
            r = str(ent.get("right") or "").upper()
            try:
                k = float(ent.get("strike")) if ent.get("strike") is not None else None
            except Exception:
                k = None
            st = str(ent.get("secType") or "")
            if st == "STK" or r == "":
                stock_flag = True
            if r == "C":
                call_n += 1
                if k is not None:
                    call_k.add(float(k))
            elif r == "P":
                put_n += 1
                if k is not None:
                    put_k.add(float(k))

        all_k = sorted(call_k.union(put_k))
        res["strikes"].append("/".join(fmt(x) for x in all_k) if all_k else "")
        res["call_strikes"].append("/".join(fmt(x) for x in sorted(call_k)) if call_k else "")
        res["put_strikes"].append("/".join(fmt(x) for x in sorted(put_k)) if put_k else "")
        res["call_count"].append(int(call_n))
        res["put_count"].append(int(put_n))
        res["has_stock_leg"].append(bool(stock_flag))
        res["__strike_source"].append(source_tag)

    for k, v in res.items():
        df[k] = v

    # Optional debug
    try:
        if os.getenv("PE_DEBUG_COMBOS") == "1":
            io_core.save(df.copy(), "combos_enriched_debug", "csv", config_core.settings.output_dir)
            df = df.drop(columns=["__strike_source"], errors="ignore")
    except Exception:
        pass
    return df

def get_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Trades report and combos export")
    parser.add_argument("--executions-csv", dest="exec_csv", default=None)
    parser.add_argument("--debug-combos", action="store_true")
    parser.add_argument(
        "--debug-intent",
        action="store_true",
        help="Emit trades_intent_debug.csv with per-leg matching details for intent tagging",
    )
    parser.add_argument(
        "--prior-positions-csv",
        default=None,
        help="Explicit prior positions CSV to override auto selection",
    )
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--summary-only", action="store_true")
    parser.add_argument("--cluster-window-sec", type=int, default=60)
    cli_helpers.add_common_output_args(parser, include_excel=True)
    cli_helpers.add_common_debug_args(parser)
    return parser


def main(argv: list[str] | None = None) -> Dict[str, Any]:
    parser = get_arg_parser()
    args = parser.parse_args(argv)

    if args.summary_only:
        args.no_files = True
    if args.debug_combos:
        os.environ["PE_DEBUG_COMBOS"] = "1"

    formats = cli_helpers.decide_file_writes(
        args,
        json_only_default=True,
        defaults={"csv": bool(args.output_dir), "excel": False},
    )
    outdir = cli_helpers.resolve_output_dir(args.output_dir)
    quiet, _pretty = cli_helpers.resolve_quiet(args.no_pretty)

    with RunLog(script="trades_report", args=vars(args), output_dir=outdir) as rl:
        df_exec: pd.DataFrame | None = None
        df_open: pd.DataFrame | None = None
        if args.exec_csv:
            try:
                df_exec = pd.read_csv(args.exec_csv)
            except Exception as exc:  # pragma: no cover - defensive
                print(f"❌ Failed to read executions CSV: {exc}")
                return {}
        else:
            t = _load_trades()
            if t is None:
                return {}
            df_exec = t
            try:
                df_open = _load_open_orders()
            except Exception:
                df_open = None

        n_total = len(df_exec) if isinstance(df_exec, pd.DataFrame) else 0
        since_dt = _parse_when(args.since)
        until_dt = _parse_when(args.until)
        df_exec = _filter_by_date(df_exec, since_dt, until_dt, col="datetime")
        n_kept = len(df_exec)
        earliest_exec_ts = _get_earliest_exec_ts(df_exec)

        pos_like = _build_positions_like_df(df_exec, None)
        uvals: list[str] = []
        if not pos_like.empty and "underlying" in pos_like.columns:
            try:
                uvals = sorted(
                    {
                        str(x)
                        for x in pos_like["underlying"].dropna().tolist()
                        if str(x)
                    }
                )
            except Exception:
                uvals = []
        try:
            m = pd.to_numeric(pos_like.get("multiplier", 0), errors="coerce").fillna(0)
            qty = pd.to_numeric(pos_like.get("qty", 0), errors="coerce").fillna(0)
            price = pd.to_numeric(pos_like.get("price", 0), errors="coerce").fillna(0)
            net_credit_debit = float((-price * qty * m).sum())
        except Exception:
            net_credit_debit = 0.0

        with rl.time("cluster"):
            clusters_df, debug_rows = _cluster_executions(df_exec, int(args.cluster_window_sec))
        k_total = len(clusters_df)
        combo_clusters = int((clusters_df.get("structure") != "synthetic").sum())

        # Ensure previous positions snapshot strictly older than earliest exec when possible
        search_dirs: list[Path] = [outdir]
        try:
            if args.exec_csv:
                from pathlib import Path as _P
                search_dirs.append(_P(args.exec_csv).expanduser().resolve().parent)
        except Exception:
            pass
        search_dirs.append(Path(config_core.settings.output_dir))
        td = Path("tests/data")
        if td.exists():
            search_dirs.append(td)

        prev_positions_df, prior_path = _ensure_prev_positions_quiet(
            earliest_exec_ts, outdir, getattr(args, "prior_positions_csv", None), search_dirs
        )

        debug_intent_rows: list = []
        combos_df = _detect_and_enrich_trades_combos(
            df_exec, df_open, prev_positions_df, debug_intent_rows if getattr(args, "debug_intent", False) else None, clusters_df
        )
        c_total = len(combos_df) if isinstance(combos_df, pd.DataFrame) else 0

        # Build intent summaries for JSON/meta (independent of file writes)
        try:
            df_all_counts = df_exec.copy()
            if isinstance(df_open, pd.DataFrame) and not df_open.empty:
                df_all_counts = pd.concat([df_all_counts, df_open], ignore_index=True, sort=False)
            df_all_counts["position_effect"] = _compute_streaming_effect(df_all_counts, prev_positions_df)
        except Exception:
            df_all_counts = pd.DataFrame(columns=["position_effect"])
        rows_counts = _intent_counts(df_all_counts.get("position_effect") if isinstance(df_all_counts, pd.DataFrame) else None)
        combos_counts = _intent_counts(combos_df.get("position_effect") if isinstance(combos_df, pd.DataFrame) and not combos_df.empty else None)
        if isinstance(combos_df, pd.DataFrame) and not combos_df.empty and "underlying" in combos_df.columns:
            gb = combos_df.groupby("underlying", dropna=False)
            intent_by_und = pd.DataFrame({
                "underlying": [u for u, _ in gb],
                "position_effect": [_choose_underlying_effect(g) for _, g in gb],
            })
        elif isinstance(df_all_counts, pd.DataFrame) and "symbol" in df_all_counts.columns:
            tmp = df_all_counts.rename(columns={"symbol": "underlying"})
            gb = tmp.groupby("underlying", dropna=False)
            intent_by_und = pd.DataFrame({
                "underlying": [u for u, _ in gb],
                "position_effect": [_choose_underlying_effect(g) for _, g in gb],
            })
        else:
            intent_by_und = pd.DataFrame(columns=["underlying", "position_effect"])

        outputs: Dict[str, str] = {}
        written: list[Path] = []
        with rl.time("write_outputs"):
            df_all: pd.DataFrame | None = None
            if formats.get("csv") or formats.get("excel"):
                df_all = df_exec.copy()
                if isinstance(df_open, pd.DataFrame) and not df_open.empty:
                    df_all = pd.concat([df_all, df_open], ignore_index=True, sort=False)
                # Prefer vectorized streaming intent
                df_all["position_effect"] = _compute_streaming_effect(df_all, prev_positions_df)
                df_all = _attach_intent_flags(df_all)
                combos_df = _attach_intent_flags(combos_df)

            if formats.get("csv") and df_all is not None:
                path_report = io_core.save(df_all, "trades_report", "csv", outdir)
                outputs["trades_report"] = str(path_report)
                written.append(path_report)
                path_combos = _save_trades_combos(combos_df, fmt="csv", outdir=outdir)
                outputs["trades_combos"] = str(path_combos)
                written.append(path_combos)
                path_clusters = io_core.save(clusters_df, "trades_clusters", "csv", outdir)
                outputs["trades_clusters"] = str(path_clusters)
                written.append(path_clusters)
                # Intent summary CSVs
                intent_tbl = pd.DataFrame([rows_counts], index=["rows"]).assign(scope="rows")
                intent_tbl2 = pd.DataFrame([combos_counts], index=["combos"]).assign(scope="combos")
                intent_summary_df = pd.concat([intent_tbl, intent_tbl2], axis=0, ignore_index=True)
                cols = ["scope", "Open", "Close", "Roll", "Mixed", "Unknown"]
                for c in cols:
                    if c not in intent_summary_df.columns:
                        intent_summary_df[c] = 0
                intent_summary_df = intent_summary_df[cols]
                path_is = core_io.save(intent_summary_df, "trades_intent_summary", "csv", outdir)
                outputs["trades_intent_summary"] = str(path_is)
                rl.add_outputs([path_is])
                if not intent_by_und.empty:
                    path_iu = core_io.save(intent_by_und, "trades_intent_by_underlying", "csv", outdir)
                    outputs["trades_intent_by_underlying"] = str(path_iu)
                    rl.add_outputs([path_iu])
                if args.debug_timings or os.getenv("PE_DEBUG") == "1":
                    dbg_path = io_core.save(debug_rows, "trades_clusters_debug", "csv", outdir)
                    outputs["trades_clusters_debug"] = str(dbg_path)
                    written.append(dbg_path)
                # Optional intent debug
                if getattr(args, "debug_intent", False) and debug_intent_rows:
                    try:
                        df_dbg = pd.DataFrame(debug_intent_rows)
                        dbg2 = core_io.save(df_dbg, "trades_intent_debug", "csv", outdir)
                        outputs["trades_intent_debug"] = str(dbg2)
                        written.append(dbg2)
                    except Exception:
                        pass
                if args.debug_timings and rl.timings:
                    tpath = io_core.save(pd.DataFrame(rl.timings), "timings", fmt="csv", outdir=outdir)
                    outputs["timings"] = str(tpath)
                    written.append(tpath)

            if formats.get("excel") and df_all is not None:
                try:
                    import openpyxl  # type: ignore  # noqa: F401
                except Exception:
                    print("⚠️ openpyxl not installed; skipping XLSX export", file=sys.stderr)
                else:
                    xlsx_path = outdir / "trades_report.xlsx"
                    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
                        df_all.to_excel(writer, sheet_name="Rows", index=False)
                        if isinstance(clusters_df, pd.DataFrame) and not clusters_df.empty:
                            clusters_df.to_excel(writer, sheet_name="Clusters", index=False)
                        if isinstance(combos_df, pd.DataFrame) and not combos_df.empty:
                            combos_df.to_excel(writer, sheet_name="Combos", index=False)
                    outputs["trades_report_xlsx"] = str(xlsx_path)
                    written.append(xlsx_path)

        rl.add_outputs(written)
        # Attach meta: intent counts and top combos by realized P&L
        try:
            top_list = []
            if isinstance(clusters_df, pd.DataFrame) and not clusters_df.empty:
                tmp = clusters_df.copy()
                try:
                    tmp = tmp.reindex(tmp["pnl"].abs().sort_values(ascending=False).index)
                except Exception:
                    tmp = tmp.sort_values("pnl", ascending=False)
                for _, r in tmp.head(5).iterrows():
                    top_list.append({
                        "underlying": str(r.get("underlying")),
                        "structure": str(r.get("structure")),
                        "legs_n": int(r.get("legs_n", 0) or 0),
                        "pnl": float(r.get("pnl", 0.0) or 0.0),
                        "start": str(r.get("start")),
                        "end": str(r.get("end")),
                    })
        except Exception:
            top_list = []
        try:
            rl.add_meta({
                "intent": {"rows": rows_counts, "combos": combos_counts, "by_underlying": intent_by_und.to_dict(orient="records") if isinstance(intent_by_und, pd.DataFrame) else []},
                "top_combos_pnl": top_list,
            })
        except Exception:
            pass
        manifest_path = rl.finalize(write=bool(written))

        meta: Dict[str, Any] = {"script": "trades_report"}
        if "trades_report_xlsx" in outputs:
            meta["outputs"] = {"trades_report_xlsx": outputs["trades_report_xlsx"]}
        # intent meta counters
        try:
            total_id = int(sum(1 for r in debug_intent_rows if r.get("match_mode") == "id"))
            total_exact = int(sum(1 for r in debug_intent_rows if r.get("match_mode") == "attr_exact"))
            total_tol = int(sum(1 for r in debug_intent_rows if r.get("match_mode") == "attr_tol"))
            total_unmatched = int(sum(1 for r in debug_intent_rows if r.get("match_mode") == "no_match"))
        except Exception:
            total_id = total_exact = total_tol = total_unmatched = 0
        meta["intent"] = {
            "prior_snapshot_path": str(prior_path) if prior_path else "",
            "matched_legs_id": total_id,
            "matched_legs_attr_exact": total_exact,
            "matched_legs_attr_tol": total_tol,
            "unmatched_legs": total_unmatched,
        }
        if args.debug_timings:
            meta["timings"] = rl.timings
        # enrich meta with intent summaries for programmatic use
        meta.setdefault("intent", {})
        meta["intent"]["rows"] = rows_counts
        meta["intent"]["combos"] = combos_counts
        meta["intent"]["by_underlying"] = (
            intent_by_und.to_dict(orient="records") if isinstance(intent_by_und, pd.DataFrame) else []
        )
        summary = json_helpers.report_summary(
            {"executions": n_kept, "clusters": k_total, "combos": combo_clusters},
            outputs=outputs,
            meta=meta,
        )
        if earliest_exec_ts is not None and (prev_positions_df is None or len(prev_positions_df) == 0):
            summary.setdefault("warnings", []).append(
                "No prior positions snapshot found before earliest execution; intent may be less accurate."
            )
        if manifest_path:
            summary["outputs"].append(str(manifest_path))

        # Human-friendly intent glance
        if not quiet:
            def _fmt(d):
                return f"Open {d.get('Open',0)}, Close {d.get('Close',0)}, Roll {d.get('Roll',0)}, Mixed {d.get('Mixed',0)}, Unknown {d.get('Unknown',0)}"
            print(f"Intent (rows):   {_fmt(rows_counts)}")
            print(f"Intent (combos): {_fmt(combos_counts)}")

        if args.json:
            cli_helpers.print_json(summary, quiet)
        return summary


# ───── Date parsing & filtering helpers (import-safe) ─────
def _parse_when(s: str | None) -> datetime | None:
    """
    Parse a date/datetime string.
    Accepts YYYY-MM-DD (local midnight) or full ISO.
    Uses dateparser if available; otherwise falls back to fromisoformat.
    Returns naive datetime in local time for consistent comparisons.
    """
    if not s:
        return None
    s = s.strip()
    if not s:
        return None
    # Try dateparser for flexibility if available
    try:
        import dateparser  # type: ignore

        dt = dateparser.parse(s)
        if dt is not None:
            return dt.replace(tzinfo=None)
    except Exception:
        pass
    # Fallback to ISO-like handling
    try:
        if len(s) == 10 and s.count("-") == 2:
            # YYYY-MM-DD → midnight
            y, m, d = map(int, s.split("-"))
            return datetime(y, m, d)
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _filter_by_date(
    df: pd.DataFrame,
    since: datetime | None,
    until: datetime | None,
    col: str = "datetime",
) -> pd.DataFrame:
    """
    Ensure df[col] exists and is datetime-like (parse if needed), then filter inclusive:
      since <= col <= until
    If only date is provided, interpret:
      since_date -> 00:00:00
      until_date -> 23:59:59.999999
    If col missing or all NaT, return df unchanged but record a warning.
    """
    if df is None or df.empty:
        return df
    d = df.copy()
    if col not in d.columns:
        # try common alternatives
        for alt in ("time", "timestamp"):
            if alt in d.columns:
                try:
                    d[col] = pd.to_datetime(d[alt], errors="coerce")
                except Exception:
                    d[col] = pd.NaT
                break
    if col not in d.columns:
        logger.warning("trades_report: datetime column missing; skipping date filter")
        return d
    try:
        d[col] = pd.to_datetime(d[col], errors="coerce")
    except Exception:
        pass
    if d[col].isna().all():
        logger.warning("trades_report: all datetime values are NaT; skipping date filter")
        return d

    # Interpret pure-date 'until' as end-of-day if time looks like midnight
    if until is not None and (
        until.hour == 0 and until.minute == 0 and until.second == 0 and until.microsecond == 0
    ):
        until = until.replace(hour=23, minute=59, second=59, microsecond=999_999)

    mask = pd.Series([True] * len(d), index=d.index)
    if since is not None:
        mask &= d[col] >= since
    if until is not None:
        mask &= d[col] <= until
    return d.loc[mask].copy()


if __name__ == "__main__":  # pragma: no cover - exercised by CLI tests
    main()
