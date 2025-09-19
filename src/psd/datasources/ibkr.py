"""IBKR datasource wrappers for the Portfolio Sentinel Dashboard.

The helpers in this module keep the IBKR integration light-weight so unit
tests can patch behaviour without touching the network.  Production callers
are expected to provide live objects (``ib_insync.IB``) while tests can inject
pragmatic stubs.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from functools import lru_cache
from typing import Any, Literal

from . import yfin

logger = logging.getLogger(__name__)

MarketDataMode = Literal["live", "delayed", "auto"]

_MARKET_DATA_MODES: dict[str, int] = {"live": 1, "delayed": 4}
_ENTITLEMENT_CODES = {10167, 354, 162, 200}
_LAST_MARKET_MODE: str | None = None
_MARK_BACKFILLS: set[str] = set()
_GREEKS_WARNED: set[str] = set()


@lru_cache(maxsize=1)
def _rules_cfg() -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        with open("config/rules.yaml", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _safe_float(value: Any) -> float | None:
    try:
        out = float(value)
    except Exception:
        return None
    if math.isnan(out):
        return None
    return out


def _normalize_expiry(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        cleaned = value.strip().replace("-", "").replace("/", "")
        return cleaned[:8]
    for attr in ("to_pydatetime", "to_datetime"):
        if hasattr(value, attr):
            try:
                value = getattr(value, attr)()
            except Exception:
                pass
    if isinstance(value, datetime):
        return value.strftime("%Y%m%d")
    return str(value)


def _underlying_mark(row: Any) -> float | None:
    if not hasattr(row, "get"):
        return None
    for key in (
        "underlying_price",
        "underlyingPrice",
        "underlying_mark",
        "underlyingMark",
        "underlying_last",
        "underlyingLast",
    ):
        if key in row:
            val = _safe_float(row.get(key))
            if val is not None:
                return val
    return None


def is_entitlement_error(err_code: int) -> bool:
    """Return True when *err_code* matches known IB entitlement failures."""
    try:
        return int(err_code) in _ENTITLEMENT_CODES
    except Exception:
        return False


def _extract_error_code(exc: BaseException) -> int | None:
    for attr in ("errorCode", "code", "errCode"):
        val = getattr(exc, attr, None)
        if val is None:
            continue
        try:
            return int(val)
        except Exception:
            continue
    return None


def mkt_data_timeout(sec: float) -> Callable[[], bool]:
    """Return a callable that evaluates to ``True`` once *sec* elapsed."""
    deadline = time.monotonic() + max(sec, 0.0)

    def _expired() -> bool:
        return time.monotonic() >= deadline

    return _expired


def set_market_data_mode(
    mode: MarketDataMode,
    *,
    client: Any | None = None,
    timeout: float | None = None,
    has_ticks: Callable[[], bool] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> str:
    """Request the desired market-data mode and return the effective mode.

    ``mode`` may be ``"live"``, ``"delayed"`` or ``"auto"``.  When ``auto`` is
    requested the helper attempts live data first and falls back to delayed
    quotes when entitlement errors are observed or no ticks arrive before the
    timeout expires.
    """
    global _LAST_MARKET_MODE

    target = str(mode or "auto").strip().lower()
    if target not in ("live", "delayed", "auto"):
        target = "auto"

    def _req(mtype: str) -> bool:
        if not client or not hasattr(client, "reqMarketDataType"):
            return True
        try:
            result = client.reqMarketDataType(_MARKET_DATA_MODES[mtype])
        except Exception as exc:  # pragma: no cover - network runtime
            logger.debug("reqMarketDataType(%s) failed: %s", mtype, exc)
            raise
        return False if result is False else True

    if target in ("live", "delayed"):
        _req(target)
        _LAST_MARKET_MODE = target
        return target

    effective = "live"
    timeout_val = timeout if timeout is not None else 2.0
    sleeper = sleep or time.sleep

    try:
        ok = _req("live")
    except Exception as exc:
        code = _extract_error_code(exc)
        if code is not None and is_entitlement_error(code):
            logger.warning("IBKR live market data entitlement missing (code %s); switching to delayed.", code)
        else:
            logger.debug("reqMarketDataType(live) raised %s; using delayed data.", exc)
        effective = "delayed"
    else:
        if not ok:
            effective = "delayed"

    if effective == "live" and has_ticks is not None:
        deadline = time.monotonic() + max(timeout_val, 0.0)
        while time.monotonic() < deadline:
            try:
                if has_ticks():
                    break
            except Exception:
                break
            sleeper(0.05)
        else:
            logger.warning("No live ticks within %.2fs – falling back to delayed market data.", timeout_val)
            effective = "delayed"

    if effective == "delayed":
        _req("delayed")

    _LAST_MARKET_MODE = effective
    return effective


def consume_mark_backfills() -> list[str]:
    """Return and clear the list of symbols whose marks were backfilled."""
    global _MARK_BACKFILLS
    symbols = sorted(_MARK_BACKFILLS)
    _MARK_BACKFILLS.clear()
    return symbols


def _resolve_cfg(cfg: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    base = _rules_cfg()
    ibkr_cfg: dict[str, Any] = {}
    fill_cfg: dict[str, Any] = {}
    if isinstance(base.get("ibkr"), dict):
        ibkr_cfg.update(base["ibkr"])
    if isinstance(base.get("fill"), dict):
        fill_cfg.update(base["fill"])
    if cfg is None:
        return ibkr_cfg, fill_cfg
    if isinstance(cfg.get("ibkr"), dict):
        ibkr_cfg.update(cfg["ibkr"])
    if isinstance(cfg.get("fill"), dict):
        fill_cfg.update(cfg["fill"])
    return ibkr_cfg, fill_cfg


def _iter_rows(df: Any) -> Iterable[Any]:
    try:
        return list(df.iterrows())
    except Exception:
        return []


def get_positions(
    cfg: dict[str, Any] | None = None,
    *,
    mode: MarketDataMode | None = None,
) -> list[dict[str, Any]]:
    """Return PSD position dicts sourced from ``portfolio_greeks`` snapshots."""
    ibkr_cfg, fill_cfg = _resolve_cfg(cfg or {})
    market_mode = (
        str(mode or (cfg or {}).get("market_data_mode") or ibkr_cfg.get("market_data_mode", "auto"))
        .strip()
        .lower()
    )
    if market_mode not in ("live", "delayed", "auto"):
        market_mode = "auto"
    timeout_sec = float(ibkr_cfg.get("mktdata_timeout_sec", 2.0) or 0.0)
    greeks_timeout = float(ibkr_cfg.get("greeks_timeout_sec", 5.0) or 0.0)

    client = None
    if isinstance(cfg, dict):
        client = cfg.get("ib_client") or cfg.get("ibkr_client")
    has_ticks = cfg.get("ib_has_ticks") if isinstance(cfg, dict) else None
    tick_probe = has_ticks if callable(has_ticks) else None

    try:
        set_market_data_mode(market_mode, client=client, timeout=timeout_sec, has_ticks=tick_probe)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to negotiate IBKR market data mode (%s): %s", market_mode, exc)

    try:
        from portfolio_exporter.scripts import portfolio_greeks as pg  # type: ignore
    except Exception:
        return []

    try:
        df = pg.load_positions_sync()  # pragma: no cover - network
        if df is None:
            return []
    except RuntimeError as exc:  # pragma: no cover - defensive
        logger.warning("load_positions_sync failed: %s", exc)
        return []
    except Exception:
        return []

    try:
        df = df.copy()
    except Exception:
        return []

    required = ["symbol", "underlying", "secType", "qty", "price", "right", "strike", "expiry"]
    for col in required:
        if col not in df.columns:
            df[col] = None

    positions: list[dict[str, Any]] = []
    missing_equity_marks: list[tuple[int, str]] = []
    missing_greeks: set[str] = set()

    try:
        eq_mask = df["secType"].astype(str).isin(["STK", "ETF"])
        qty_mask = df["qty"].fillna(0) != 0
        eq_df = df[eq_mask & qty_mask]
    except Exception:
        eq_df = df.iloc[0:0]

    for _, row in _iter_rows(eq_df):
        sym = str(row.get("symbol") or row.get("underlying") or "").upper()
        if not sym:
            continue
        qty = int(_safe_float(row.get("qty")) or 0)
        mark = _safe_float(row.get("price"))
        pos = {
            "uid": f"STK-{sym}",
            "symbol": sym,
            "sleeve": "core",
            "kind": "equity",
            "qty": qty,
            "mark": mark,
        }
        if mark is None:
            missing_equity_marks.append((len(positions), sym))
        positions.append(pos)

    try:
        opt_mask = df["secType"].astype(str).isin(["OPT", "FOP"])
        opt_df = df[opt_mask & qty_mask]
    except Exception:
        opt_df = df.iloc[0:0]

    if not opt_df.empty:
        from ..models import OptionLeg

        grouped: dict[str, dict[str, Any]] = {}
        for _, row in _iter_rows(opt_df):
            sym = str(row.get("underlying") or row.get("symbol") or "").upper()
            if not sym:
                continue
            strike = _safe_float(row.get("strike"))
            qty = int(_safe_float(row.get("qty")) or 0)
            price = _safe_float(row.get("price")) or 0.0
            expiry = _normalize_expiry(row.get("expiry"))
            delta_val = None
            for key in ("delta", "option_delta", "optionDelta", "Delta"):
                if key in row and row.get(key) is not None:
                    delta_val = _safe_float(row.get(key))
                    if delta_val is not None:
                        break
            if delta_val is None:
                exposure = _safe_float(row.get("delta_exposure"))
                multiplier = _safe_float(row.get("multiplier")) or 100.0
                under_mark = _underlying_mark(row) or 0.0
                if exposure is not None and multiplier and under_mark and qty:
                    try:
                        delta_val = exposure / (multiplier * under_mark * qty)
                    except Exception:
                        delta_val = None
            if delta_val is None:
                missing_greeks.add(sym)

            try:
                leg = OptionLeg(
                    symbol=sym,
                    expiry=expiry or "",
                    right=(str(row.get("right") or "").upper() or "C"),
                    strike=float(strike or 0.0),
                    qty=int(qty),
                    price=float(price),
                    delta=float(delta_val) if delta_val is not None else None,
                )
            except Exception:
                continue

            bucket = grouped.setdefault(sym, {"legs": [], "mark": None})
            bucket["legs"].append(leg)  # type: ignore[arg-type]
            under_mark = _underlying_mark(row)
            if under_mark is not None:
                bucket["mark"] = under_mark

        for sym, info in grouped.items():
            positions.append(
                {
                    "uid": f"OPT-{sym}",
                    "symbol": sym,
                    "sleeve": "theta",
                    "kind": "option",
                    "qty": 0,
                    "mark": info.get("mark"),
                    "legs": info.get("legs", []),
                }
            )

    if missing_equity_marks and bool(fill_cfg.get("allow_yf_equity_marks", True)):
        symbols = [sym for _, sym in missing_equity_marks]
        fills = yfin.fill_equity_marks_from_yf(symbols)
        for idx, sym in missing_equity_marks:
            price = fills.get(sym)
            if price is None:
                continue
            try:
                positions[idx]["mark"] = float(price)
            except Exception:
                continue
            _MARK_BACKFILLS.add(sym)

    for sym in sorted(missing_greeks):
        if sym in _GREEKS_WARNED:
            continue
        logger.warning(
            "Greeks unavailable for %s within %.1fs; leaving legs with null values.", sym, greeks_timeout
        )
        _GREEKS_WARNED.add(sym)

    return positions


def fetch_marks(
    symbols: Sequence[str],
    cfg: dict[str, Any] | None = None,
    *,
    mode: MarketDataMode | None = None,
) -> dict[str, float | None]:
    """Return the latest marks for ``symbols`` using ``get_positions``."""
    wanted = {s.strip().upper() for s in symbols if s}
    if not wanted:
        return {}
    data = get_positions(cfg, mode=mode)
    marks: dict[str, float | None] = {}
    for row in data:
        if row.get("kind") != "equity":
            continue
        sym = str(row.get("symbol") or "").upper()
        if sym in wanted:
            marks[sym] = row.get("mark")  # type: ignore[assignment]
    return marks


def fetch_greeks(
    symbols: Sequence[str],
    cfg: dict[str, Any] | None = None,
    *,
    mode: MarketDataMode | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Return lightweight per-leg greek snapshots for ``symbols``."""
    wanted = {s.strip().upper() for s in symbols if s}
    if not wanted:
        return {}
    data = get_positions(cfg, mode=mode)
    out: dict[str, list[dict[str, Any]]] = {}
    for row in data:
        if row.get("kind") != "option":
            continue
        sym = str(row.get("symbol") or "").upper()
        if sym not in wanted:
            continue
        legs = []
        for leg in row.get("legs", []) or []:
            legs.append(
                {
                    "expiry": getattr(leg, "expiry", ""),
                    "right": getattr(leg, "right", ""),
                    "strike": getattr(leg, "strike", None),
                    "qty": getattr(leg, "qty", None),
                    "delta": getattr(leg, "delta", None),
                }
            )
        out[sym] = legs
    return out
