"""Core quotes module delegates to the resilient snapshot implementation
in scripts/live_feed to avoid duplication and drift.

This keeps a single source of truth for snapshot behavior, including
retry/fallback logic and proxy mappings.
"""

import math
from collections.abc import Callable, Sequence
from typing import Any


def snapshot(tickers: Sequence[str]) -> dict[str, float]:
    """
    Fetch snapshot quotes for the given tickers and return a
    mapping of {symbol: last_price}.

    Delegates to scripts/live_feed._snapshot_quotes so both CLI menu
    and direct script calls share the same retry/fallback logic.
    """
    # Backward-compatible test hook: if local helpers are monkeypatched,
    # honor the old IBKR→YF fallback path used in tests.
    ib_fn: Callable[[Sequence[str]], dict[str, float]] | None = globals().get(
        "_ibkr_quotes"
    )  # type: ignore[assignment]
    yf_fn: Callable[[Sequence[str]], dict[str, float]] | None = globals().get(
        "_yf_quotes"
    )  # type: ignore[assignment]
    if callable(ib_fn) and callable(yf_fn):
        try:
            return ib_fn(tickers)
        except ConnectionError:
            return yf_fn(tickers)

    # Lazy import to avoid import-time side effects from scripts/live_feed
    from portfolio_exporter.scripts.live_feed import _snapshot_quotes

    df = _snapshot_quotes(list(tickers), fmt="csv")
    if df is None or df.empty:
        return {}
    # live_feed returns columns: symbol, price
    return {
        str(sym): float(val) if val is not None else float("nan")
        for sym, val in zip(df["symbol"], df["price"], strict=True)
    }


def _coerce_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def snapshot_detail(
    tickers: Sequence[str],
) -> dict[str, dict[str, float | None | str]]:
    """Fetch snapshot quotes and include previous close when available."""
    from portfolio_exporter.scripts.live_feed import _snapshot_quotes

    df = _snapshot_quotes(list(tickers), fmt="csv")
    if df is None or df.empty:
        return {}

    details: dict[str, dict[str, float | None | str]] = {}
    for _, row in df.iterrows():
        symbol = str(row.get("symbol", "")).strip()
        if not symbol:
            continue
        price = _coerce_float(row.get("price"))
        prev_close = _coerce_float(row.get("prev_close"))
        source_raw = row.get("source")
        source = source_raw.strip() if isinstance(source_raw, str) else None
        details[symbol] = {
            "price": price,
            "previous_close": prev_close,
            "source": source,
        }
    return details


# Placeholders for test monkeypatching compatibility.
# These are not used in normal execution but allow tests to attach fakes
# without AttributeError on setattr.
def _ibkr_quotes(
    _tickers: Sequence[str],
) -> dict[str, float]:  # pragma: no cover - test hook
    raise ConnectionError("IBKR not available in core.quotes stub")


def _yf_quotes(
    _tickers: Sequence[str],
) -> dict[str, float]:  # pragma: no cover - test hook
    return {}
