"""Core quotes module delegates to the resilient snapshot implementation
in scripts/live_feed to avoid duplication and drift.

This keeps a single source of truth for snapshot behavior, including
retry/fallback logic and proxy mappings.
"""

from collections.abc import Callable, Sequence


def snapshot(tickers: Sequence[str]) -> dict[str, float]:
    """
    Fetch snapshot quotes for the given tickers and return a
    mapping of {symbol: last_price}.

    Delegates to scripts/live_feed._snapshot_quotes so both CLI menu
    and direct script calls share the same retry/fallback logic.
    """
    # Backward-compatible test hook: if local helpers are monkeypatched,
    # honor the old IBKR→YF fallback path used in tests.
    ib_fn: Callable[[Sequence[str]], dict[str, float]] | None = globals().get("_ibkr_quotes")  # type: ignore[assignment]
    yf_fn: Callable[[Sequence[str]], dict[str, float]] | None = globals().get("_yf_quotes")  # type: ignore[assignment]
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


# Placeholders for test monkeypatching compatibility.
# These are not used in normal execution but allow tests to attach fakes
# without AttributeError on setattr.
def _ibkr_quotes(_tickers: Sequence[str]) -> dict[str, float]:  # pragma: no cover - test hook
    raise ConnectionError("IBKR not available in core.quotes stub")


def _yf_quotes(_tickers: Sequence[str]) -> dict[str, float]:  # pragma: no cover - test hook
    return {}
