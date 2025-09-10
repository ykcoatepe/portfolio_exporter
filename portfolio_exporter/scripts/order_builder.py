"""order_builder.py – Interactive ticket wizard for simple strategies."""

from __future__ import annotations

import builtins
import datetime as dt
import datetime as _dt
import json
import pathlib
from typing import Any, Dict, List, Optional, Tuple

try:
    from prompt_toolkit import prompt  # retained for optional environments
except Exception:  # pragma: no cover - optional dependency
    def prompt(message: str) -> str:  # type: ignore
        return input(message)

try:
    from yfinance import Ticker
except Exception:  # pragma: no cover - optional dependency
    Ticker = None  # type: ignore

from portfolio_exporter.core.config import settings
try:
    from portfolio_exporter.core.input import parse_order_line
except Exception:  # pragma: no cover - optional dependency for interactive shorthand
    def parse_order_line(raw):  # type: ignore
        return None
from portfolio_exporter.core.ui import banner_delta_theta, console, prompt_input
from rich.table import Table
try:  # pragma: no cover - ib_insync optional in tests
    from portfolio_exporter.core.ib import quote_option, quote_stock  # type: ignore
except Exception:  # pragma: no cover
    quote_option = quote_stock = None  # type: ignore
try:  # optional auto-selection engine
    from portfolio_exporter.core import preset_engine as _pe  # type: ignore
except Exception:  # pragma: no cover
    _pe = None  # type: ignore

# Expose prompt_toolkit.prompt via a dotted builtins attribute for tests
setattr(builtins, "prompt_toolkit.prompt", prompt)

# ── expiry normaliser ---------------------------------------------------------
_expiry_cache: dict[str, list[str]] = {}

# ── repo memory helpers (lightweight) -----------------------------------------
from pathlib import Path as _Path
import json as _json
import os as _os


def _memory_path() -> _Path:
    return _Path(".codex/memory.json")


def _load_wizard_prefs() -> Dict[str, Any]:
    p = _memory_path()
    try:
        if not p.exists():
            return {}
        data = _json.loads(p.read_text())
        prefs = data.get("preferences", {}).get("order_builder_wizard", {})
        if isinstance(prefs, dict):
            return prefs
    except Exception:
        pass
    return {}


def _save_wizard_prefs(upd: Dict[str, Any]) -> None:
    p = _memory_path()
    try:
        data: Dict[str, Any] = {}
        if p.exists():
            try:
                data = _json.loads(p.read_text())
            except Exception:
                data = {}
        prefs = data.setdefault("preferences", {}).setdefault("order_builder_wizard", {})
        prefs.update(upd)
        tmp = p.with_suffix(".json.tmp")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        with tmp.open("w", encoding="utf-8") as f:
            _json.dump(data, f, sort_keys=True, separators=(",", ":"))
            f.flush()
            _os.fsync(f.fileno())
        _os.replace(tmp, p)
    except Exception:
        # Non-fatal
        pass


def _monthly_regular_expiry(year: int, month: int) -> _dt.date:
    """Return the regular monthly options expiry (3rd Friday) for year-month.

    Notes: Does not account for market holidays shifting to Thursday; this is
    sufficient for quick ticket building and matches typical expectations.
    """
    first = _dt.date(year, month, 1)
    # Friday is 4 (Mon=0)
    first_friday_day = ((4 - first.weekday()) % 7) + 1
    third_friday_day = first_friday_day + 14
    return _dt.date(year, month, third_friday_day)


def _nearest_expiry(symbol: str, dt_like) -> str:
    """
    Accepts str *or* datetime/date.  Returns the same string if it is listed,
    otherwise the next later available expiry for `symbol`.
    """
    # normalise to YYYY-MM-DD string
    if isinstance(dt_like, (_dt.date, _dt.datetime)):
        date_str = dt_like.strftime("%Y-%m-%d")
    else:
        date_str = str(dt_like)

    exps = _expiry_cache.get(symbol)
    if exps is None:
        exps = Ticker(symbol).options
        _expiry_cache[symbol] = exps

    if date_str in exps:
        return date_str
    # pick the first expiry after the requested date; else fall back to last
    for d in exps:
        if d > date_str:
            return d
    return exps[-1]


def _nearest_friday(on_or_after: _dt.date) -> _dt.date:
    # Monday=0 ... Sunday=6; Friday=5
    days_ahead = (4 - on_or_after.weekday()) % 7
    return on_or_after + _dt.timedelta(days=days_ahead)


def _parse_date_like(text: str) -> Optional[_dt.date]:
    # Try ISO first to avoid optional deps
    try:
        return _dt.date.fromisoformat(text)
    except Exception:
        pass
    try:  # optional dependency route
        import dateparser  # type: ignore

        dtp = dateparser.parse(text, settings={"PREFER_DATES_FROM": "future"})
        return dtp.date() if dtp else None
    except Exception:
        return None


def _parse_month_shorthand(text: str) -> Optional[_dt.date]:
    """Parse inputs like 'nov', 'nov24', 'nov-2025', '2025-11', '11/2025'.

    Returns the 3rd Friday for the given or inferred month/year.
    """
    if not text:
        return None
    raw = text.strip().lower()
    import re as _re

    # Map month tokens
    months = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "sept": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }

    # Pattern: nov, nov24, nov-24, nov-2025, nov 2025
    m = _re.match(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)(?:[\s\-/]?([0-9]{2,4}))?$", raw)
    if m:
        mon = months[m.group(1)]
        yr_s = m.group(2)
        today = _dt.date.today()
        year = today.year
        if yr_s:
            if len(yr_s) == 2:
                year = 2000 + int(yr_s)
            else:
                year = int(yr_s)
        d = _monthly_regular_expiry(year, mon)
        # If no explicit year provided and the date already passed, roll to next year
        if not yr_s and d < today:
            d = _monthly_regular_expiry(year + 1, mon)
        return d

    # Pattern: YYYY-MM, YYYY/MM
    m = _re.match(r"^([12][0-9]{3})[\-/](0?[1-9]|1[0-2])$", raw)
    if m:
        year = int(m.group(1))
        month = int(m.group(2))
        return _monthly_regular_expiry(year, month)

    # Pattern: MM/YYYY
    m = _re.match(r"^(0?[1-9]|1[0-2])[\-/]([12][0-9]{3})$", raw)
    if m:
        month = int(m.group(1))
        year = int(m.group(2))
        return _monthly_regular_expiry(year, month)

    return None


def _normalize_expiry(symbol: str, raw: str | None) -> str:
    """Normalize expiry to YYYY-MM-DD without requiring network.

    Attempts to parse the input; on failure, uses the nearest Friday from today.
    If yfinance is available at runtime and the exact date isn't listed, users
    still get the provided date; we avoid remote normalization here to keep the
    builder predictable offline.
    """
    if not raw:
        d = _nearest_friday(_dt.date.today() + _dt.timedelta(weeks=2))
        return d.isoformat()
    # First support month-only shorthands mapping to regular monthly expiry
    d = _parse_month_shorthand(str(raw))
    if not d:
        d = _parse_date_like(str(raw))
    if not d:
        d = _nearest_friday(_dt.date.today() + _dt.timedelta(weeks=2))
    return d.isoformat()


def _ask(question: str, default: Optional[str] = None) -> str | None:
    """Prompt for a value with Live-aware echo so typing is visible.

    Uses ``prompt_input`` which pauses the global StatusBar (if active)
    to avoid Rich Live repaint hiding the user's keystrokes. Falls back
    to a plain input when no StatusBar is running.
    """
    default_str = f" [{default}]" if default else ""
    try:
        resp = prompt_input(f"{question}{default_str}: ")
    except Exception:
        # Ultimate fallback – prompt_toolkit or builtin input
        ask_fn = getattr(builtins, "prompt_toolkit.prompt", prompt)
        resp = ask_fn(f"{question}{default_str}: ")
    if isinstance(resp, str) and resp.strip().lower() == "q":
        raise RuntimeError("abort")
    return resp or default


def _price_leg(
    symbol: str, expiry: str | None, strike: float | None, right: str | None
) -> Dict[str, float]:
    """Return pricing for a leg, with graceful offline fallbacks.

    - Options: prefers IBKR quote via quote_option; if unavailable, returns a
      zeroed quote to keep the flow usable offline.
    - Stock: prefers IBKR quote via quote_stock; if unavailable, returns a
      zeroed quote and default greeks so we can still build a ticket.
    """
    try:
        if right in {"C", "P"}:
            if quote_option is None:
                raise RuntimeError("quote_option not available")
            # If an expiry was provided, use it as-is to avoid network normalization.
            # Only resolve to the nearest listed expiry when it's missing.
            expiry = expiry or _nearest_expiry(symbol, expiry)
            return quote_option(symbol, expiry or "", float(strike), right)
        if quote_stock is None:
            raise RuntimeError("quote_stock not available")
        data = quote_stock(symbol)
        data.update({
            "delta": 1.0,
            "gamma": 0.0,
            "theta": 0.0,
            "vega": 0.0,
            "iv": 0.0,
        })
        return data
    except Exception:
        # Offline or quoting backend not present: return a safe, zeroed quote
        return {
            "bid": 0.0,
            "ask": 0.0,
            "mid": 0.0,
            "delta": 0.0 if right in {"C", "P"} else 1.0,
            "gamma": 0.0,
            "theta": 0.0,
            "vega": 0.0,
            "iv": 0.0,
        }


def _render_preview_table(rows: List[Dict[str, Any]]) -> Table:
    tbl = Table(show_header=True, header_style="bold")
    tbl.add_column("Underlying", justify="left")
    tbl.add_column("Strategy", justify="left")
    tbl.add_column("Expiry", justify="left")
    tbl.add_column("Right", justify="center")
    tbl.add_column("Strike", justify="right")
    tbl.add_column("Qty", justify="right")
    tbl.add_column("Mid", justify="right")
    tbl.add_column("Limit", justify="right")
    tbl.add_column("Δ", justify="right")
    tbl.add_column("Θ", justify="right")
    tbl.add_column("Vega", justify="right")
    tbl.add_column("IV", justify="right")
    tbl.add_column("Total Mid", justify="right")
    tbl.add_column("Total Limit", justify="right")
    tbl.add_column("Spread Mid", justify="right")
    tbl.add_column("Spread Limit", justify="right")

    def fmt(x, nd=2):
        try:
            return f"{float(x):.{nd}f}"
        except Exception:
            return str(x)

    for r in rows:
        tbl.add_row(
            str(r.get("underlying", "")),
            str(r.get("strategy", "")),
            str(r.get("expiry", "")),
            str(r.get("right", "")),
            ("" if r.get("strike", "") == "" else fmt(r.get("strike"), 2)),
            str(r.get("qty", "")),
            ("" if r.get("mid", "") == "" else fmt(r.get("mid"), 2)),
            ("" if r.get("limit", "") == "" else fmt(r.get("limit"), 2)),
            ("" if r.get("delta", "") == "" else fmt(r.get("delta"), 2)),
            ("" if r.get("theta", "") == "" else fmt(r.get("theta"), 2)),
            ("" if r.get("vega", "") == "" else fmt(r.get("vega"), 2)),
            ("" if r.get("iv", "") == "" else fmt(r.get("iv"), 2)),
            ("" if r.get("cost_mid", "") == "" else fmt(r.get("cost_mid"), 2)),
            ("" if r.get("cost_limit", "") == "" else fmt(r.get("cost_limit"), 2)),
            ("" if r.get("spread_mid", "") == "" else fmt(r.get("spread_mid"), 2)),
            ("" if r.get("spread_limit", "") == "" else fmt(r.get("spread_limit"), 2)),
        )
    return tbl


# ── strategy builders --------------------------------------------------------


def _base_ticket(
    strategy: str,
    symbol: str,
    expiry: str,
    qty: int,
    strikes: List[float],
    right: str,
    account: str | None = None,
):
    return {
        "timestamp": dt.datetime.utcnow().isoformat(),
        "strategy": strategy,
        "underlying": symbol,
        "expiry": expiry,
        "qty": qty,
        "strikes": strikes,
        "right": right,
        "account": account or settings.default_account,
        "legs": [],
    }


def build_vertical(
    symbol: str,
    expiry: str,
    right: str,
    strikes: List[float],
    qty: int,
    account: str | None = None,
    *,
    credit: bool | None = None,
):
    k_low, k_high = sorted(strikes)
    ticket = _base_ticket("vertical", symbol, expiry, qty, [k_low, k_high], right, account)
    # Default orientation to preserve legacy behavior if credit/debit not provided:
    # - Calls default to debit (buy low, sell high)
    # - Puts default to credit (sell high, buy low)
    if credit is None:
        is_credit = (right == "P")
    else:
        is_credit = bool(credit)
    if right == "C":
        if is_credit:
            # Credit call: sell low / buy high
            legs = [
                {"secType": "OPT", "right": "C", "strike": k_low, "qty": -qty, "expiry": expiry},
                {"secType": "OPT", "right": "C", "strike": k_high, "qty": qty, "expiry": expiry},
            ]
        else:
            # Debit call: buy low / sell high
            legs = [
                {"secType": "OPT", "right": "C", "strike": k_low, "qty": qty, "expiry": expiry},
                {"secType": "OPT", "right": "C", "strike": k_high, "qty": -qty, "expiry": expiry},
            ]
    else:  # Puts
        if is_credit:
            # Credit put: sell high / buy low
            legs = [
                {"secType": "OPT", "right": "P", "strike": k_high, "qty": -qty, "expiry": expiry},
                {"secType": "OPT", "right": "P", "strike": k_low, "qty": qty, "expiry": expiry},
            ]
        else:
            # Debit put: buy high / sell low
            legs = [
                {"secType": "OPT", "right": "P", "strike": k_high, "qty": qty, "expiry": expiry},
                {"secType": "OPT", "right": "P", "strike": k_low, "qty": -qty, "expiry": expiry},
            ]
    ticket["legs"] = legs
    return ticket


def build_iron_condor(
    symbol: str,
    expiry: str,
    strikes: List[float],
    qty: int,
    account: str | None = None,
):
    k1, k2, k3, k4 = sorted(strikes)
    ticket = _base_ticket(
        "iron_condor", symbol, expiry, qty, [k1, k2, k3, k4], "", account
    )
    legs = [
        {"secType": "OPT", "right": "P", "strike": k2, "qty": qty, "expiry": expiry},
        {"secType": "OPT", "right": "P", "strike": k1, "qty": -qty, "expiry": expiry},
        {"secType": "OPT", "right": "C", "strike": k3, "qty": qty, "expiry": expiry},
        {"secType": "OPT", "right": "C", "strike": k4, "qty": -qty, "expiry": expiry},
    ]
    ticket["legs"] = legs
    return ticket


def build_butterfly(
    symbol: str,
    expiry: str,
    right: str,
    strikes: List[float],
    qty: int,
    account: str | None = None,
):
    k1, k2, k3 = sorted(strikes)
    ticket = _base_ticket("butterfly", symbol, expiry, qty, [k1, k2, k3], right, account)
    legs = [
        {"secType": "OPT", "right": right, "strike": k1, "qty": qty, "expiry": expiry},
        {
            "secType": "OPT",
            "right": right,
            "strike": k2,
            "qty": -2 * qty,
            "expiry": expiry,
        },
        {"secType": "OPT", "right": right, "strike": k3, "qty": qty, "expiry": expiry},
    ]
    ticket["legs"] = legs
    return ticket


def build_calendar(
    symbol: str,
    expiry: str,
    right: str,
    exp_near: str,
    exp_far: str,
    strike: float,
    qty: int,
    account: str | None = None,
):
    near, far = sorted([exp_near, exp_far])
    expiry = far  # ticket expiry = far
    ticket = _base_ticket("calendar", symbol, expiry, qty, [strike], right, account)
    legs = [
        {"secType": "OPT", "right": right, "strike": strike, "qty": -qty, "expiry": near},
        {"secType": "OPT", "right": right, "strike": strike, "qty": qty, "expiry": far},
    ]
    ticket["legs"] = legs
    return ticket


def build_diagonal(
    symbol: str,
    expiry: str,
    right: str,
    exp_near: str,
    exp_far: str,
    strike_near: float,
    strike_far: float,
    qty: int,
    account: str | None = None,
):
    near, far = sorted([exp_near, exp_far])
    expiry = far  # ticket expiry = far
    ticket = _base_ticket("diagonal", symbol, expiry, qty, [strike_near, strike_far], right, account)
    legs = [
        {"secType": "OPT", "right": right, "strike": strike_near, "qty": -qty, "expiry": near},
        {"secType": "OPT", "right": right, "strike": strike_far, "qty": qty, "expiry": far},
    ]
    ticket["legs"] = legs
    return ticket


def build_straddle(
    symbol: str,
    expiry: str,
    strike: float,
    qty: int,
    account: str | None = None,
):
    ticket = _base_ticket("straddle", symbol, expiry, qty, [strike], "", account)
    legs = [
        {"secType": "OPT", "right": "C", "strike": strike, "qty": qty, "expiry": expiry},
        {"secType": "OPT", "right": "P", "strike": strike, "qty": qty, "expiry": expiry},
    ]
    ticket["legs"] = legs
    return ticket


def build_strangle(
    symbol: str,
    expiry: str,
    put_strike: float,
    call_strike: float,
    qty: int,
    account: str | None = None,
):
    k_put, k_call = sorted([put_strike, call_strike])
    ticket = _base_ticket(
        "strangle", symbol, expiry, qty, [k_put, k_call], "", account
    )
    legs = [
        {"secType": "OPT", "right": "P", "strike": k_put, "qty": qty, "expiry": expiry},
        {"secType": "OPT", "right": "C", "strike": k_call, "qty": qty, "expiry": expiry},
    ]
    ticket["legs"] = legs
    return ticket


def build_covered_call(
    symbol: str,
    expiry: str,
    call_strike: float,
    qty: int,
    account: str | None = None,
    stock_multiplier: int = 100,
):
    ticket = _base_ticket(
        "covered_call", symbol, expiry, qty, [call_strike], "", account
    )
    legs = [
        {
            "secType": "OPT",
            "right": "C",
            "strike": call_strike,
            "qty": -abs(qty),
            "expiry": expiry,
        },
        {"secType": "STK", "qty": stock_multiplier * abs(qty)},
    ]
    ticket["legs"] = legs
    return ticket


# ---- preset helpers ---------------------------------------------------------

def build_preset(
    preset: str,
    symbol: str,
    expiry: str,
    qty: int,
    width: float = 5.0,
    wings: float = 5.0,
    account: str | None = None,
) -> Dict[str, Any]:
    """Return a ticket for simple strategy presets.

    Presets avoid external lookups by using synthetic strikes around 100.
    """
    base = 100.0
    if preset == "bull_put":
        short, long = base, base - width
        legs = [
            {"secType": "OPT", "right": "P", "strike": short, "qty": -qty, "expiry": expiry},
            {"secType": "OPT", "right": "P", "strike": long, "qty": qty, "expiry": expiry},
        ]
        strikes = [long, short]
        right = "P"
    elif preset == "bear_call":
        short, long = base, base + width
        legs = [
            {"secType": "OPT", "right": "C", "strike": short, "qty": -qty, "expiry": expiry},
            {"secType": "OPT", "right": "C", "strike": long, "qty": qty, "expiry": expiry},
        ]
        strikes = [short, long]
        right = "C"
    elif preset == "bull_call":
        long_, short = base, base + width
        legs = [
            {"secType": "OPT", "right": "C", "strike": long_, "qty": qty, "expiry": expiry},
            {"secType": "OPT", "right": "C", "strike": short, "qty": -qty, "expiry": expiry},
        ]
        strikes = [long_, short]
        right = "C"
    elif preset == "bear_put":
        long_, short = base, base - width
        legs = [
            {"secType": "OPT", "right": "P", "strike": long_, "qty": qty, "expiry": expiry},
            {"secType": "OPT", "right": "P", "strike": short, "qty": -qty, "expiry": expiry},
        ]
        strikes = [short, long_]
        right = "P"
    elif preset == "iron_condor":
        put_long = base - 2 * wings
        put_short = base - wings
        call_short = base + wings
        call_long = base + 2 * wings
        legs = [
            {"secType": "OPT", "right": "P", "strike": put_short, "qty": -qty, "expiry": expiry},
            {"secType": "OPT", "right": "P", "strike": put_long, "qty": qty, "expiry": expiry},
            {"secType": "OPT", "right": "C", "strike": call_short, "qty": -qty, "expiry": expiry},
            {"secType": "OPT", "right": "C", "strike": call_long, "qty": qty, "expiry": expiry},
        ]
        strikes = [put_long, put_short, call_short, call_long]
        right = ""
    elif preset == "iron_fly":
        put_long = base - wings
        call_long = base + wings
        center = base
        legs = [
            {"secType": "OPT", "right": "P", "strike": center, "qty": -qty, "expiry": expiry},
            {"secType": "OPT", "right": "P", "strike": put_long, "qty": qty, "expiry": expiry},
            {"secType": "OPT", "right": "C", "strike": center, "qty": -qty, "expiry": expiry},
            {"secType": "OPT", "right": "C", "strike": call_long, "qty": qty, "expiry": expiry},
        ]
        strikes = [put_long, center, call_long]
        right = ""
    elif preset == "calendar":
        far = expiry
        near_dt = dt.datetime.fromisoformat(far) - dt.timedelta(days=30)
        near = near_dt.date().isoformat()
        strike = base
        legs = [
            {"secType": "OPT", "right": "C", "strike": strike, "qty": -qty, "expiry": near},
            {"secType": "OPT", "right": "C", "strike": strike, "qty": qty, "expiry": far},
        ]
        strikes = [strike]
        right = "C"
        expiry = far
    else:  # pragma: no cover - defensive
        raise ValueError(f"Unknown preset {preset}")

    ticket = _base_ticket(preset, symbol, expiry, qty, strikes, right, account)
    ticket["legs"] = legs
    return ticket


def compute_risk_summary(ticket: Dict[str, Any]) -> Dict[str, Any] | None:
    """Compute basic max gain/loss and breakevens for option combos."""

    legs = ticket.get("legs", [])
    if not legs:
        return None
    net_calls = sum(leg.get("qty", 0) for leg in legs if leg.get("right") == "C")
    if net_calls:
        return None

    # Price legs for spread price
    net = 0.0
    for leg in legs:
        q = _price_leg(ticket["underlying"], leg.get("expiry"), leg.get("strike"), leg.get("right"))
        net += leg.get("qty", 0) * q.get("mid", 0)

    strikes = [leg.get("strike") for leg in legs if leg.get("strike") is not None]
    if len(strikes) < 2:
        return None
    width = max(strikes) - min(strikes)
    if len(legs) == 2:
        short = next((l for l in legs if l.get("qty", 0) < 0), None)
        long = next((l for l in legs if l.get("qty", 0) > 0), None)
        if not short or not long:
            return None
        if net < 0:  # credit
            credit = -net
            breakeven = (
                short["strike"] + credit
                if short.get("right") == "C"
                else short["strike"] - credit
            )
            return {
                "max_gain": credit,
                "max_loss": width - credit,
                "breakevens": [breakeven],
            }
        debit = net
        breakeven = (
            long["strike"] + debit
            if long.get("right") == "C"
            else long["strike"] - debit
        )
        return {
            "max_gain": width - debit,
            "max_loss": debit,
            "breakevens": [breakeven],
        }
    elif len(legs) == 4:
        # Treat as iron condor / fly credit structure
        credit = -net if net < 0 else 0
        shorts = [l for l in legs if l.get("qty", 0) < 0]
        short_put = next((l for l in shorts if l.get("right") == "P"), None)
        short_call = next((l for l in shorts if l.get("right") == "C"), None)
        put_longs = [l for l in legs if l.get("right") == "P" and l.get("qty", 0) > 0]
        call_longs = [l for l in legs if l.get("right") == "C" and l.get("qty", 0) > 0]
        width_put = (
            short_put["strike"] - put_longs[0]["strike"]
            if short_put and put_longs
            else 0
        )
        width_call = (
            call_longs[0]["strike"] - short_call["strike"]
            if short_call and call_longs
            else 0
        )
        width = max(width_put, width_call)
        breakevens = []
        if short_put and short_call:
            breakevens = [short_put["strike"] - credit, short_call["strike"] + credit]
        return {
            "max_gain": credit,
            "max_loss": width - credit,
            "breakevens": breakevens,
        }
    return None


def run() -> bool:
    raw = prompt_input("Order (shorthand, Enter to step-through): ").strip()
    parsed = parse_order_line(raw) if raw else None

    today = dt.date.today()
    expiry_default = (today + dt.timedelta(weeks=2)).isoformat()
    strat_default = "cc"
    underlying_default = ""
    qty_default = "1"
    strikes_default = ""
    right: Optional[str] = None

    if parsed:
        underlying_default = parsed.underlying
        expiry_default = parsed.legs[0].expiry.isoformat()
        qty_default = str(parsed.qty)
        strikes_default = ",".join(f"{leg.strike:g}" for leg in parsed.legs)
        right = parsed.legs[0].right
        strat_default = (
            "vert" if len(parsed.legs) == 2 else ("csp" if right == "P" else "cc")
        )

    # ------------------------------------------------------------------
    # 1) STRATEGY
    # Skip the live prompt when the shorthand gave us everything we need,
    # regardless of TTY.  Only ask if *something* was missing/ambiguous.
    # ------------------------------------------------------------------
    have_all_fields = bool(parsed)

    if parsed and len(parsed.legs) == 2:
        strat = "vert"
    else:
        if have_all_fields:
            strat = strat_default
        else:
            strat = (
                _ask(
                    "Strategy (cc/csp/vert/ic/fly/cal/strad/stran/cov)",
                    strat_default,
                )
                or "cc"
            ).lower()

    # ------------------------------------------------------------------
    # 2) UNDERLYING
    # ------------------------------------------------------------------
    if parsed and len(parsed.legs) == 2:
        underlying = underlying_default
    else:
        if have_all_fields:
            underlying = underlying_default
        else:
            underlying = (_ask("Underlying", underlying_default) or "").upper()
            if not underlying:
                console.print("[red]Underlying is required[/red]")
                return False

    # ------------------------------------------------------------------
    # 3) EXPIRY
    # ------------------------------------------------------------------
    if parsed:
        expiry = expiry_default
    else:
        expiry_in = _ask("Expiry (YYYY-MM-DD or DTE days)", expiry_default) or expiry_default
        if str(expiry_in).strip().isdigit():
            expiry = (today + dt.timedelta(days=int(str(expiry_in).strip()))).isoformat()
        else:
            expiry = _normalize_expiry(underlying, expiry_in)

    # ------------------------------------------------------------------
    # 4) QTY & STRIKES
    # ------------------------------------------------------------------
    is_credit_choice: Optional[bool] = None

    if parsed:
        qty = int(qty_default)
        strikes = [leg.strike for leg in parsed.legs]
    else:
        qty = int(_ask("Contracts", qty_default) or qty_default)
        # For verticals, ask orientation before strikes to make intent explicit
        if strat == "vert":
            if not right:
                right = ((_ask("Right (C/P)", "C") or "C").upper())
            kind = (_ask("Vertical type (debit/credit)", "debit") or "debit").lower()
            is_credit_choice = kind.startswith("c")
        # Optional Auto suggestions for supported strategies (Phase A)
        auto_used = False
        if _pe is not None and strat in {"vert", "ic", "iron_condor", "cal", "calendar", "fly", "butterfly"}:
            auto = (_ask("Auto suggestions from live data? (Y/n)", "Y") or "Y").strip().lower()
            if auto in {"", "y"}:
                # Load/prompt persisted preferences
                _prefs = _load_wizard_prefs()
                profile = (_ask("Profile (conservative/balanced/aggressive)", str(_prefs.get("profile", "balanced"))) or _prefs.get("profile", "balanced")).lower()
                avoid_default = "Y" if _prefs.get("avoid_earnings", True) else "N"
                avoid_e = (_ask("Avoid earnings within 7 days? (Y/n)", avoid_default) or avoid_default).strip().lower() in {"", "y"}
                min_oi_def = str(_prefs.get("min_oi", 200))
                min_volume_def = str(_prefs.get("min_volume", 50))
                max_spread_def = str(_prefs.get("max_spread_pct", 0.02))
                min_oi = int((_ask("Min OI", min_oi_def) or min_oi_def))
                min_volume = int((_ask("Min Volume", min_volume_def) or min_volume_def))
                try:
                    max_spread_pct = float((_ask("Max spread fraction of mid", max_spread_def) or max_spread_def))
                except Exception:
                    max_spread_pct = float(max_spread_def)
                rb_in = _ask("Risk budget % of NetLiq for sizing", str(_prefs.get("risk_budget_pct", 2))) or str(_prefs.get("risk_budget_pct", 2))
                try:
                    rb_pct = float(rb_in)
                    if rb_pct > 1:
                        rb_pct = rb_pct / 100.0
                except Exception:
                    rb_pct = None
                _save_wizard_prefs({
                    "profile": profile,
                    "avoid_earnings": avoid_e,
                    "min_oi": min_oi,
                    "min_volume": min_volume,
                    "max_spread_pct": max_spread_pct,
                    "risk_budget_pct": float(rb_in) if str(rb_in).replace('.', '', 1).isdigit() else _prefs.get("risk_budget_pct", 2),
                })
                # Build candidates
                cands = []
                resolved_exp = expiry
                auto_near = None
                auto_far = None
                auto_far_strike = None
                try:
                    if strat == "vert":
                        # Map to preset-like side
                        if right == "P":
                            side = "bull_put" if is_credit_choice else "bear_put"
                        else:
                            side = "bear_call" if is_credit_choice else "bull_call"
                        if side in {"bull_put", "bear_call"}:
                            cands = _pe.suggest_credit_vertical(
                                underlying,
                                expiry,
                                side,
                                profile,
                                rules=_pe.LiquidityRules(min_oi=min_oi, min_volume=min_volume, max_spread_pct=max_spread_pct),
                                avoid_earnings=avoid_e,
                                earnings_window_days=7,
                                risk_budget_pct=rb_pct,
                            )
                        else:
                            cands = _pe.suggest_debit_vertical(
                                underlying,
                                expiry,
                                side,
                                profile,
                                rules=_pe.LiquidityRules(min_oi=min_oi, min_volume=min_volume, max_spread_pct=max_spread_pct),
                                avoid_earnings=avoid_e,
                                earnings_window_days=7,
                            )
                    elif strat in {"fly", "butterfly"}:
                        # Ensure right is known
                        if not right:
                            right = ((_ask("Right (C/P)", "C") or "C").upper())
                        cands = _pe.suggest_butterfly(
                            underlying,
                            expiry,
                            right,
                            profile,
                            rules=_pe.LiquidityRules(min_oi=min_oi, min_volume=min_volume, max_spread_pct=max_spread_pct),
                            avoid_earnings=avoid_e,
                            earnings_window_days=7,
                        )
                    else:  # iron condor
                        if strat in {"ic", "iron_condor"}:
                            cands = _pe.suggest_iron_condor(
                                underlying,
                                expiry,
                                profile,
                                rules=_pe.LiquidityRules(min_oi=min_oi, min_volume=min_volume, max_spread_pct=max_spread_pct),
                                avoid_earnings=avoid_e,
                                earnings_window_days=7,
                                risk_budget_pct=rb_pct,
                            )
                        else:  # calendar/diagonal
                            if not right:
                                right = ((_ask("Right (C/P)", "C") or "C").upper())
                            so_def = str(_prefs.get("strike_offset", 0))
                            try:
                                strike_offset = int((_ask("Diagonal far strike offset steps (0=calendar)", so_def) or so_def))
                            except Exception:
                                strike_offset = int(so_def)
                            _save_wizard_prefs({"strike_offset": strike_offset})
                            cands = _pe.suggest_calendar(
                                underlying,
                                expiry,
                                right,
                                profile,
                                rules=_pe.LiquidityRules(min_oi=min_oi, min_volume=min_volume, max_spread_pct=max_spread_pct),
                                avoid_earnings=avoid_e,
                                earnings_window_days=7,
                                strike_offset=strike_offset,
                            )
                    if cands:
                        resolved_exp = cands[0].get("expiry", expiry)
                except Exception:
                    cands = []
                if cands:
                    from rich.table import Table as _Tbl
                    tbl = _Tbl(title=f"Candidates ({underlying} {resolved_exp})")
                    tbl.add_column("#", justify="right")
                    tbl.add_column("Strikes", justify="left")
                    tbl.add_column("Type", justify="center")
                    tbl.add_column("Price", justify="right")
                    tbl.add_column("Width", justify="right")
                    tbl.add_column("Risk", justify="right")
                    tbl.add_column("POP", justify="right")
                    tbl.add_column("Qty*", justify="right")
                    for i, c in enumerate(cands, 1):
                        ks = sorted({float(leg.get("strike")) for leg in c.get("legs", [])})
                        typ = "CR" if "credit" in c else ("DR" if "debit" in c else "CR")
                        price = c.get("credit", c.get("debit", 0.0))
                        riskv = c.get("max_loss", c.get("debit", 0.0))
                        tbl.add_row(
                            str(i),
                            ",".join(f"{k:g}" for k in ks),
                            typ,
                            f"{price:.2f}",
                            f"{c.get('width',0):.2f}",
                            f"{riskv:.2f}",
                            f"{c.get('pop_proxy',0):.2f}",
                            str(c.get('suggested_qty','')),
                        )
                    console.print(tbl)
                    sel = (_ask("Select candidate # (or Enter to skip)", "") or "").strip()
                    if sel.isdigit() and 1 <= int(sel) <= len(cands):
                        pick = cands[int(sel) - 1]
                        expiry = pick.get("expiry", resolved_exp)
                        ks = sorted({float(leg.get("strike")) for leg in pick.get("legs", [])})
                        if strat == "vert" and len(ks) >= 2:
                            strikes = [ks[0], ks[1]]
                            # suggested qty if provided
                            if pick.get("suggested_qty"):
                                use_auto = (_ask(f"Use suggested qty {int(pick.get('suggested_qty'))}? (Y/n)", "Y") or "Y").strip().lower()
                                if use_auto in {"", "y"}:
                                    qty = int(pick.get("suggested_qty"))
                            auto_used = True
                        elif strat in {"ic", "iron_condor"} and len(ks) >= 4:
                            strikes = ks[:4]
                            if pick.get("suggested_qty"):
                                use_auto = (_ask(f"Use suggested qty {int(pick.get('suggested_qty'))}? (Y/n)", "Y") or "Y").strip().lower()
                                if use_auto in {"", "y"}:
                                    qty = int(pick.get("suggested_qty"))
                            auto_used = True
                        elif strat in {"fly", "butterfly"} and len(ks) >= 3:
                            strikes = ks[:3]
                            if pick.get("suggested_qty"):
                                use_auto = (_ask(f"Use suggested qty {int(pick.get('suggested_qty'))}? (Y/n)", "Y") or "Y").strip().lower()
                                if use_auto in {"", "y"}:
                                    qty = int(pick.get("suggested_qty"))
                            auto_used = True
                        elif strat in {"cal", "calendar"} and len(ks) >= 1:
                            # Store near/far defaults for calendar and optional far strike for diagonal
                            auto_near = pick.get("near") or None
                            auto_far = pick.get("far") or expiry
                            auto_far_strike = pick.get("strike_far", ks[0])
                            strikes = [pick.get("strike_near", ks[0])]
                            if pick.get("suggested_qty"):
                                use_auto = (_ask(f"Use suggested qty {int(pick.get('suggested_qty'))}? (Y/n)", "Y") or "Y").strip().lower()
                                if use_auto in {"", "y"}:
                                    qty = int(pick.get("suggested_qty"))
                            auto_used = True
        # Strategy-specific strikes collection
        if not locals().get("strikes", []):
            strikes = []
        if not auto_used and strat in {"cc", "csp", "vert"}:
            strikes_in = (
                _ask("Strike(s) (comma-sep)", strikes_default) or ""
            ).replace(" ", "")
            strikes = [float(s) for s in strikes_in.split(",") if s]
        elif not auto_used and strat in {"ic", "iron_condor"}:
            raw = _ask("Strikes P_low,P_high,C_low,C_high", "") or ""
            ks = [float(s.strip()) for s in raw.replace(" ", "").split(",") if s]
            if len(ks) != 4:
                raise ValueError("Iron condor requires four strikes")
            strikes = ks
        elif strat in {"fly", "butterfly"}:
            raw = _ask("Strikes low,mid,high", "") or ""
            ks = [float(s.strip()) for s in raw.replace(" ", "").split(",") if s]
            if len(ks) != 3:
                raise ValueError("Butterfly requires three strikes")
            strikes = ks
        elif strat in {"cal", "calendar"}:
            # strike gathered later as single float unless Auto provided
            if not auto_used:
                strikes = []
        elif strat in {"strad", "straddle"}:
            raw = _ask("Strike", strikes_default or "") or ""
            strikes = [float(raw)] if raw else []
        elif strat in {"stran", "strangle"}:
            raw = _ask("Strikes put,call", "") or ""
            ks = [float(s.strip()) for s in raw.replace(" ", "").split(",") if s]
            if len(ks) != 2:
                raise ValueError("Strangle requires two strikes (put,call)")
            strikes = ks
        elif strat in {"cov", "covered_call"}:
            raw = _ask("Call strike", strikes_default or "") or ""
            strikes = [float(raw)] if raw else []
        else:
            strikes = []

    if not right:
        if strat in {"csp", "strad", "straddle", "stran", "strangle", "ic", "iron_condor", "fly", "butterfly", "cov", "covered_call"}:
            # handled per-leg or strategy
            right = ""
        else:
            right = "P" if strat == "csp" else "C"

    # For verticals, make right explicit when using the wizard
    if strat == "vert" and not parsed and not right:
        right = ((_ask("Right (C/P)", "C") or "C").upper())

    legs: List[Dict[str, Any]] = []
    if strat == "cc":
        legs.append(
            {
                "symbol": underlying,
                "expiry": None,
                "strike": None,
                "right": None,
                "qty": qty * 100,
                "mult": 1,
            }
        )
        # short covered call -> short CALL option
        legs.append(
            {
                "symbol": underlying,
                "qty": -qty,
                "right": "C",
                "expiry": expiry,
                "strike": float(strikes[0]),
                "mult": 100,
            }
        )
    elif strat == "csp":
        # long cash-secured put -> long PUT option
        legs.append(
            {
                "symbol": underlying,
                "qty": qty,
                "right": "P",
                "expiry": expiry,
                "strike": float(strikes[0]),
                "mult": 100,
            }
        )
    elif strat == "vert":
        if len(strikes) != 2:
            raise ValueError("Vertical strategy requires two strikes")
        k_low, k_high = sorted([float(strikes[0]), float(strikes[1])])
        # Optional prompt when not using shorthand: choose credit/debit (or use prior choice)
        is_credit = bool(is_credit_choice)
        if not parsed and is_credit_choice is None:
            kind = (_ask("Vertical type (debit/credit)", "debit") or "debit").lower()
            is_credit = kind.startswith("c")

        if right == "C":
            # Calls: debit = buy low / sell high; credit = sell low / buy high
            q_low, q_high = (qty, -qty) if not is_credit else (-qty, qty)
            legs.append(
                {
                    "symbol": underlying,
                    "expiry": expiry,
                    "strike": k_low,
                    "right": right,
                    "qty": q_low,
                    "mult": 100,
                }
            )
            legs.append(
                {
                    "symbol": underlying,
                    "expiry": expiry,
                    "strike": k_high,
                    "right": right,
                    "qty": q_high,
                    "mult": 100,
                }
            )
        else:
            # Puts: credit = sell high / buy low; debit = buy high / sell low
            q_low, q_high = (-qty, qty) if is_credit else (qty, -qty)
            legs.append(
                {
                    "symbol": underlying,
                    "expiry": expiry,
                    "strike": k_low,
                    "right": right,
                    "qty": q_low,
                    "mult": 100,
                }
            )
            legs.append(
                {
                    "symbol": underlying,
                    "expiry": expiry,
                    "strike": k_high,
                    "right": right,
                    "qty": q_high,
                    "mult": 100,
                }
            )
    elif strat in {"ic", "iron_condor"}:
        k1, k2, k3, k4 = strikes
        # Use builder to ensure orientation logic parity
        t = build_iron_condor(underlying, expiry, [k1, k2, k3, k4], qty, None)
        legs = [
            {
                "symbol": underlying,
                "expiry": leg.get("expiry"),
                "strike": leg.get("strike"),
                "right": leg.get("right"),
                "qty": leg.get("qty"),
                "mult": 100 if leg.get("right") else 1,
            }
            for leg in t["legs"]
        ]
    elif strat in {"fly", "butterfly"}:
        # ask/right selection if not inferred
        r = (_ask("Right (C/P)", "C") or "C").upper()
        k1, k2, k3 = strikes
        t = build_butterfly(underlying, expiry, r, [k1, k2, k3], qty, None)
        legs = [
            {
                "symbol": underlying,
                "expiry": leg.get("expiry"),
                "strike": leg.get("strike"),
                "right": leg.get("right"),
                "qty": leg.get("qty"),
                "mult": 100,
            }
            for leg in t["legs"]
        ]
    elif strat in {"cal", "calendar"}:
        r = (_ask("Right (C/P)", "C") or "C").upper() if not right else right
        near_in = _ask("Near expiry (YYYY-MM-DD)", auto_near or expiry) or (auto_near or expiry)
        far_in = _ask("Far expiry (YYYY-MM-DD)", auto_far or expiry) or (auto_far or expiry)
        near = _normalize_expiry(underlying, near_in)
        far = _normalize_expiry(underlying, far_in)
        if not strikes:
            raise ValueError("Calendar requires a strike")
        strike = float(strikes[0])
        if auto_far_strike is not None and float(auto_far_strike) != float(strike):
            t = build_diagonal(underlying, far, r, near, far, strike, float(auto_far_strike), qty, None)
        else:
            t = build_calendar(underlying, far, r, near, far, strike, qty, None)
        legs = [
            {
                "symbol": underlying,
                "expiry": leg.get("expiry"),
                "strike": leg.get("strike"),
                "right": leg.get("right"),
                "qty": leg.get("qty"),
                "mult": 100,
            }
            for leg in t["legs"]
        ]
    elif strat in {"strad", "straddle"}:
        if not strikes:
            raise ValueError("Straddle requires a strike")
        t = build_straddle(underlying, expiry, float(strikes[0]), qty, None)
        legs = [
            {
                "symbol": underlying,
                "expiry": leg.get("expiry"),
                "strike": leg.get("strike"),
                "right": leg.get("right"),
                "qty": leg.get("qty"),
                "mult": 100,
            }
            for leg in t["legs"]
        ]
    elif strat in {"stran", "strangle"}:
        put_k, call_k = strikes
        t = build_strangle(underlying, expiry, float(put_k), float(call_k), qty, None)
        legs = [
            {
                "symbol": underlying,
                "expiry": leg.get("expiry"),
                "strike": leg.get("strike"),
                "right": leg.get("right"),
                "qty": leg.get("qty"),
                "mult": 100,
            }
            for leg in t["legs"]
        ]
    elif strat in {"cov", "covered_call"}:
        if not strikes:
            raise ValueError("Covered call requires a call strike")
        t = build_covered_call(underlying, expiry, float(strikes[0]), qty, None)
        # stock leg mult=1, option leg mult=100
        legs = [
            {
                "symbol": underlying,
                "expiry": leg.get("expiry"),
                "strike": leg.get("strike"),
                "right": leg.get("right"),
                "qty": leg.get("qty"),
                "mult": 100 if leg.get("right") in {"C", "P"} else 1,
            }
            for leg in t["legs"]
        ]
    else:
        raise ValueError(f"Unknown strategy {strat}")

    cfg = getattr(settings, "order_builder", None)
    slippage = getattr(cfg, "slippage", 0.05)
    delta_cap = getattr(cfg, "delta_cap", float("inf"))
    theta_cap = getattr(cfg, "theta_cap", float("-inf"))
    confirm_caps = getattr(cfg, "confirm_above_caps", True)

    mid_prices: List[float] = []
    net_mid = net_limit = 0.0
    net_delta = net_theta = net_gamma = net_vega = 0.0
    rows: List[Dict[str, Any]] = []
    for leg in legs:
        price = _price_leg(
            leg["symbol"], leg.get("expiry"), leg.get("strike"), leg.get("right")
        )
        leg.update(price)
        mid_prices.append(price["mid"])
        leg_qty = leg["qty"]
        mult = leg["mult"]
        net_mid += leg_qty * price["mid"] * mult
        net_delta += leg_qty * price["delta"] * mult
        net_theta += leg_qty * price["theta"] * mult
        net_gamma += leg_qty * price["gamma"] * mult
        net_vega += leg_qty * price["vega"] * mult
        sign = 1 if leg_qty > 0 else -1
        leg["limit"] = round(price["mid"] + slippage * sign, 2)
        cost_mid = leg_qty * price["mid"] * mult
        cost_limit = leg_qty * leg["limit"] * mult
        net_limit += cost_limit
        rows.append(
            {
                "underlying": underlying,
                "strategy": strat,
                "expiry": leg.get("expiry") or "",
                "strike": leg.get("strike") or "",
                "right": leg.get("right") or "",
                "qty": leg_qty,
                "mid": price["mid"],
                "limit": leg["limit"],
                "delta": price["delta"],
                "theta": price["theta"],
                "vega": price["vega"],
                "iv": price["iv"],
                "cost_mid": cost_mid,
                "cost_limit": cost_limit,
            }
        )

    # If all legs are options with standard 100 multiplier, compute spread prices (per contract)
    all_opts_100 = all((leg.get("right") in {"C", "P"}) and leg.get("mult") == 100 for leg in legs)
    spread_mid = (net_mid / 100.0) if all_opts_100 else ""
    spread_limit = (net_limit / 100.0) if all_opts_100 else ""

    rows.append(
        {
            "underlying": "TOTAL",
            "strategy": "",
            "expiry": "",
            "strike": "",
            "right": "",
            "qty": sum(leg["qty"] for leg in legs),
            # For pure option combos, show per-contract spread in the 'mid'/'limit' columns
            # to match how traders quote spreads; keep dollar totals in cost_*.
            "mid": spread_mid if all_opts_100 else net_mid,
            "delta": net_delta,
            "theta": net_theta,
            "vega": net_vega,
            "iv": "",
            "limit": spread_limit if all_opts_100 else net_limit,
            "cost_mid": net_mid,
            "cost_limit": net_limit,
            "spread_mid": spread_mid,
            "spread_limit": spread_limit,
        }
    )

    outdir = pathlib.Path(settings.output_dir).expanduser()
    outdir.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    preview_path = outdir / f"order_preview_{ts}.csv"
    import pandas as pd

    pd.DataFrame(rows).to_csv(preview_path, index=False)

    # Visual preview in terminal
    console.rule("Order Preview")
    console.print(_render_preview_table(rows))
    # Net summary: credit if negative cost, debit if positive; also show spread price when meaningful
    net_kind = "Credit" if net_mid < 0 else "Debit"
    if all_opts_100:
        console.print(
            f"[bold]{net_kind}[/bold] $: mid {net_mid:+.2f}  limit {net_limit:+.2f}  |  Spread: mid {spread_mid:+.2f}  limit {spread_limit:+.2f}"
        )
    else:
        console.print(
            f"[bold]{net_kind}[/bold]: mid {net_mid:+.2f}  limit {net_limit:+.2f}"
        )
    console.print(f"[dim]Saved preview: {preview_path}[/dim]")

    console.rule("Risk impact")
    banner_delta_theta(net_delta, net_theta, net_gamma, net_vega, net_mid)
    caps_warn = []
    if abs(net_delta) > delta_cap:
        caps_warn.append(f"Δ>{delta_cap}")
    if net_theta < theta_cap:
        caps_warn.append(f"Θ<{theta_cap}")

    risk_caps_ok = True
    if caps_warn and confirm_caps:
        console.print(f"[red]⚠  {' & '.join(caps_warn)}[/red]")
        risk_caps_ok = prompt_input("Proceed? (y/N): ").strip().lower() == "y"
    if not risk_caps_ok:
        console.print("Aborted.")
        return False

    out = outdir / "tickets"
    out.mkdir(parents=True, exist_ok=True)
    fn = (
        out
        / f"ticket_{underlying}_{expiry}_{dt.datetime.now().strftime('%H%M%S')}.json"
    )

    ticket = {
        "timestamp": dt.datetime.utcnow().isoformat(),
        "strategy": strat,
        "underlying": underlying,
        "expiry": expiry,
        "qty": qty,
        "strikes": strikes,
        "right": right,
        "account": settings.default_account,
        "legs": [
            {
                "symbol": leg["symbol"],
                "expiry": leg.get("expiry"),
                "strike": leg.get("strike"),
                "right": leg.get("right"),
                "qty": leg["qty"],
                "limit": leg["limit"],
            }
            for leg in legs
        ],
        "mid_prices": mid_prices,
        "net_delta": net_delta,
        "net_theta": net_theta,
        "risk_caps_ok": risk_caps_ok,
    }
    fn.write_text(json.dumps(ticket, indent=2))
    print(f"✅ Ticket saved to {fn}")
    return True


def cli(argv: List[str] | None = None) -> int:
    """Non-interactive ticket builder CLI."""
    import argparse
    try:
        from portfolio_exporter.core.io import save as io_save  # type: ignore
    except Exception:
        def io_save(obj, name, fmt="json", outdir=None):  # type: ignore
            from pathlib import Path as _P
            import json as _json
            p = _P(outdir or ".") / f"{name}.{fmt if fmt != 'excel' else 'xlsx'}"
            p.parent.mkdir(parents=True, exist_ok=True)
            if fmt == "json":
                p.write_text(_json.dumps(obj, indent=2))
            elif fmt == "csv":
                try:
                    import pandas as _pd
                    assert isinstance(obj, _pd.DataFrame)
                    obj.to_csv(p, index=False)
                except Exception:
                    p.write_text("")
            else:
                p.write_text("")
            return p
    parser = argparse.ArgumentParser(description="Build option strategy tickets")
    parser.add_argument("--strategy")
    parser.add_argument(
        "--preset",
        choices=[
            "bull_put",
            "bear_call",
            "bull_call",
            "bear_put",
            "iron_condor",
            "iron_fly",
            "calendar",
        ],
    )
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--expiry", default="")
    parser.add_argument("--expiry-near", dest="expiry_near", default=None)
    parser.add_argument("--expiry-far", dest="expiry_far", default=None)
    parser.add_argument("--right", default="")
    parser.add_argument("--strikes", default="")
    # Vertical orientation
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--credit", action="store_true", help="Build vertical as a credit spread")
    g.add_argument("--debit", action="store_true", help="Build vertical as a debit spread")
    parser.add_argument("--strike", type=float, default=None)
    parser.add_argument("--put-strike", dest="put_strike", type=float, default=None)
    parser.add_argument("--call-strike", dest="call_strike", type=float, default=None)
    parser.add_argument("--qty", type=int, default=1)
    parser.add_argument("--account", default=None)
    parser.add_argument("--width", type=float, default=5.0)
    parser.add_argument("--wings", type=float, default=5.0)
    parser.add_argument("--json", action="store_true", help="Print ticket JSON to stdout")
    parser.add_argument("--no-files", action="store_true", help="Do not write ticket files")
    # Auto-selection preview flags (for supported presets)
    parser.add_argument("--auto", action="store_true", help="Suggest strikes from live data and print candidates JSON (presets: bull_put, bear_call, bull_call, bear_put, iron_condor)")
    parser.add_argument("--wizard", action="store_true", help="Wizard-style auto preview for strategy/right/credit-debit with JSON output")
    parser.add_argument("--pick", type=int, default=None, help="When using --auto or --wizard JSON preview, pick Nth candidate and emit ticket JSON")
    parser.add_argument("--profile", default="balanced", help="Auto profile: conservative|balanced|aggressive")
    parser.add_argument("--dte", type=int, default=None, help="Days to expiry (alternative to --expiry)")
    parser.add_argument("--risk-budget-pct", dest="risk_budget_pct", type=float, default=None, help="Risk budget percent of NetLiq for suggested qty (e.g., 2 for 2%)")
    parser.add_argument("--earnings-window", dest="earnings_window", type=int, default=7, help="Avoid earnings within +/- N days in auto mode")
    parser.add_argument("--no-avoid-earnings", dest="avoid_earnings", action="store_false", help="Do not avoid earnings proximity in auto mode")
    parser.set_defaults(avoid_earnings=True)
    # Liquidity thresholds for auto mode
    parser.add_argument("--min-oi", dest="min_oi", type=int, default=200, help="Minimum open interest filter for auto selection")
    parser.add_argument("--min-volume", dest="min_volume", type=int, default=50, help="Minimum volume filter for auto selection")
    parser.add_argument(
        "--max-spread-pct",
        dest="max_spread_pct",
        type=float,
        default=0.02,
        help="Maximum bid-ask spread as a fraction of mid (e.g., 0.02 = 2%)",
    )
    parser.add_argument("--strike-offset", dest="strike_offset", type=int, default=0, help="For calendar/diagonal: far leg strike offset in steps (calls up, puts down)")
    args = parser.parse_args(argv)

    qty = int(args.qty)
    ticket: Dict[str, Any]

    # Wizard auto-preview (non-interactive)
    if args.wizard and args.auto:
        if _pe is None:
            parser.error("auto selection is unavailable (preset_engine missing)")
        if not args.strategy:
            parser.error("--strategy required for --wizard --auto")
        strat = args.strategy.lower().replace("-", "_")
        exp_in = args.expiry
        if args.dte is not None and args.dte > 0:
            d = dt.date.today() + dt.timedelta(days=int(args.dte))
            exp_in = d.isoformat()
        exp_norm = _normalize_expiry(args.symbol, exp_in)
        warn = ""
        try:
            rb_val = None
            if args.risk_budget_pct is not None:
                rb_val = float(args.risk_budget_pct)
                if rb_val > 1:
                    rb_val = rb_val / 100.0
            rules = _pe.LiquidityRules(min_oi=int(args.min_oi), min_volume=int(args.min_volume), max_spread_pct=float(args.max_spread_pct))
            if strat == "vertical":
                if not args.right:
                    parser.error("--right required for vertical wizard preview")
                side = None
                if args.right.upper() == "P":
                    side = "bull_put" if args.credit or (not args.debit and True) else "bear_put"
                else:
                    side = "bear_call" if args.credit or (not args.debit and False) else "bull_call"
                if side in {"bull_put", "bear_call"}:
                    cands = _pe.suggest_credit_vertical(args.symbol, exp_norm, side, args.profile, rules=rules, avoid_earnings=bool(args.avoid_earnings), earnings_window_days=int(args.earnings_window), risk_budget_pct=rb_val)
                else:
                    cands = _pe.suggest_debit_vertical(args.symbol, exp_norm, side, args.profile, rules=rules, avoid_earnings=bool(args.avoid_earnings), earnings_window_days=int(args.earnings_window))
            elif strat == "butterfly":
                if not args.right:
                    parser.error("--right required for butterfly wizard preview")
                cands = _pe.suggest_butterfly(args.symbol, exp_norm, args.right.upper(), args.profile, rules=rules, avoid_earnings=bool(args.avoid_earnings), earnings_window_days=int(args.earnings_window))
            elif strat == "iron_condor":
                cands = _pe.suggest_iron_condor(args.symbol, exp_norm, args.profile, rules=rules, avoid_earnings=bool(args.avoid_earnings), earnings_window_days=int(args.earnings_window), risk_budget_pct=rb_val)
            elif strat == "calendar":
                if not args.right:
                    parser.error("--right required for calendar wizard preview")
                cands = _pe.suggest_calendar(
                    args.symbol,
                    exp_norm,
                    args.right.upper(),
                    args.profile,
                    rules=rules,
                    avoid_earnings=bool(args.avoid_earnings),
                    earnings_window_days=int(args.earnings_window),
                    strike_offset=int(args.strike_offset),
                )
            else:
                parser.error("--wizard --auto currently supports vertical, butterfly, calendar and iron_condor")
        except Exception as exc:
            cands = []
            warn = f"auto selection failed: {exc}"
        result: Dict[str, Any] = {
            "ok": True,
            "wizard": True,
            "auto": True,
            "strategy": args.strategy,
            "inputs": {
                "symbol": args.symbol,
                "expiry_input": exp_in,
                "expiry": exp_norm,
                "profile": args.profile,
                "avoid_earnings": bool(args.avoid_earnings),
                "earnings_window": int(args.earnings_window),
                "risk_budget_pct": args.risk_budget_pct,
                "liquidity": {"min_oi": int(args.min_oi), "min_volume": int(args.min_volume), "max_spread_pct": float(args.max_spread_pct)},
            },
            "resolved_expiry": (cands[0].get("expiry") if cands else exp_norm),
            "candidates": cands,
            "warnings": ([warn] if warn else []),
            "meta": {"schema_id": "order_builder_wizard_auto", "schema_version": "1"},
        }
        # Pick-and-build
        if args.pick and cands and 1 <= int(args.pick) <= len(cands):
            pick = cands[int(args.pick) - 1]
            expiry = pick.get("expiry", exp_norm)
            ticket: Dict[str, Any]
            if strat == "vertical":
                ks = sorted({float(leg.get("strike")) for leg in pick.get("legs", [])})
                credit_flag = True if "credit" in pick else False if "debit" in pick else None
                ticket = build_vertical(args.symbol, expiry, args.right.upper(), ks[:2], int(args.qty), args.account, credit=credit_flag)
            elif strat == "butterfly":
                ks = sorted({float(leg.get("strike")) for leg in pick.get("legs", [])})
                ticket = build_butterfly(args.symbol, expiry, args.right.upper(), ks[:3], int(args.qty), args.account)
            elif strat == "calendar":
                ks = sorted({float(leg.get("strike")) for leg in pick.get("legs", [])})
                near = pick.get("near") or pick.get("legs")[0].get("expiry")
                far = pick.get("far") or pick.get("expiry")
                # Identify far vs near strikes
                strike_near = pick.get("strike_near", ks[0])
                strike_far = pick.get("strike_far", ks[0])
                if float(strike_near) != float(strike_far):
                    ticket = build_diagonal(args.symbol, far, args.right.upper(), near, far, float(strike_near), float(strike_far), int(args.qty), args.account)
                else:
                    ticket = build_calendar(args.symbol, far, args.right.upper(), near, far, float(strike_near), int(args.qty), args.account)
            else:  # iron condor
                ks = sorted({float(leg.get("strike")) for leg in pick.get("legs", [])})
                ticket = build_iron_condor(args.symbol, expiry, ks[:4], int(args.qty), args.account)
            result["picked"] = int(args.pick)
            result["ticket"] = ticket
        if args.json:
            print(json.dumps(result, separators=(",", ":")))
        return 0

    if args.preset:
        # Auto-preview path: return candidates instead of a ticket
        if args.auto:
            if _pe is None:
                parser.error("auto selection is unavailable (preset_engine missing)")
            side = args.preset
            if side not in {"bull_put", "bear_call", "bull_call", "bear_put", "iron_condor"}:
                parser.error("--auto supports bull_put, bear_call, bull_call, bear_put, iron_condor")
            # Resolve expiry via DTE if provided
            exp_in = args.expiry
            if args.dte is not None and args.dte > 0:
                d = dt.date.today() + dt.timedelta(days=int(args.dte))
                exp_in = d.isoformat()
            exp_norm = _normalize_expiry(args.symbol, exp_in)
            warn = ""
            try:
                rb_val = None
                if args.risk_budget_pct is not None:
                    rb_val = float(args.risk_budget_pct)
                    # If user passed 2 and intended 2%, accept as 2 -> 0.02; if they passed 0.02, keep
                    if rb_val > 1:
                        rb_val = rb_val / 100.0
                rules = None
                if _pe is not None:
                    rules = _pe.LiquidityRules(
                        min_oi=int(args.min_oi),
                        min_volume=int(args.min_volume),
                        max_spread_pct=float(args.max_spread_pct),
                    )
                if side in {"bull_put", "bear_call"}:
                    cands = _pe.suggest_credit_vertical(
                        args.symbol,
                        exp_norm,
                        side,
                        args.profile,
                        rules=rules,
                        avoid_earnings=bool(args.avoid_earnings),
                        earnings_window_days=int(args.earnings_window),
                        risk_budget_pct=rb_val,
                    )
                elif side in {"bull_call", "bear_put"}:
                    cands = _pe.suggest_debit_vertical(
                        args.symbol,
                        exp_norm,
                        side,
                        args.profile,
                        rules=rules,
                        avoid_earnings=bool(args.avoid_earnings),
                        earnings_window_days=int(args.earnings_window),
                    )
                else:  # iron_condor
                    cands = _pe.suggest_iron_condor(
                        args.symbol,
                        exp_norm,
                        args.profile,
                        rules=rules,
                        avoid_earnings=bool(args.avoid_earnings),
                        earnings_window_days=int(args.earnings_window),
                        risk_budget_pct=rb_val,
                    )
            except Exception as exc:
                cands = []
                warn = f"auto selection failed: {exc}"
            result: Dict[str, Any] = {
                "ok": True,
                "preset": args.preset,
                "auto": True,
                "inputs": {
                    "symbol": args.symbol,
                    "expiry_input": exp_in,
                    "expiry": exp_norm,
                    "profile": args.profile,
                    "avoid_earnings": bool(args.avoid_earnings),
                    "earnings_window": int(args.earnings_window),
                    "risk_budget_pct": args.risk_budget_pct,
                },
                "resolved_expiry": (cands[0].get("expiry") if cands else exp_norm),
                "candidates": cands,
                "warnings": ([warn] if warn else []),
                "meta": {"schema_id": "order_builder_auto", "schema_version": "1"},
            }
            if args.json:
                print(json.dumps(result, separators=(",", ":")))
            return 0

        exp_norm = _normalize_expiry(args.symbol, args.expiry)
        ticket = build_preset(
            args.preset,
            args.symbol,
            exp_norm,
            qty,
            width=float(args.width),
            wings=float(args.wings),
            account=args.account,
        )
    else:
        if not args.strategy:
            parser.error("--strategy required when --preset is not used")
        strat = args.strategy.lower().replace("-", "_")
        if strat == "vertical":
            strikes = [float(s) for s in args.strikes.split(",") if s]
            # Determine orientation: default (legacy) if neither flag is set
            credit_flag = None
            if args.credit:
                credit_flag = True
            elif args.debit:
                credit_flag = False
            ticket = build_vertical(
                args.symbol,
                args.expiry,
                args.right.upper(),
                strikes,
                qty,
                args.account,
                credit=credit_flag,
            )
        elif strat == "iron_condor":
            strikes = [float(s) for s in args.strikes.split(",") if s]
            ticket = build_iron_condor(args.symbol, args.expiry, strikes, qty, args.account)
        elif strat == "butterfly":
            strikes = [float(s) for s in args.strikes.split(",") if s]
            ticket = build_butterfly(
                args.symbol, args.expiry, args.right.upper(), strikes, qty, args.account
            )
        elif strat == "calendar":
            near = args.expiry_near
            far = args.expiry_far or args.expiry
            if args.expiry and "," in args.expiry:
                near, far = [p.strip() for p in args.expiry.split(",", 1)]
            if not (near and far):
                parser.error("calendar requires --expiry-near and --expiry-far or --expiry near,far")
            if args.strike is None:
                parser.error("calendar requires --strike")
            ticket = build_calendar(
                args.symbol,
                far,
                args.right.upper(),
                near,
                far,
                float(args.strike),
                qty,
                args.account,
            )
        elif strat == "straddle":
            strike = args.strike if args.strike is not None else None
            if strike is None and args.strikes:
                strike = float(args.strikes)
            if strike is None:
                parser.error("straddle requires --strike")
            ticket = build_straddle(args.symbol, args.expiry, float(strike), qty, args.account)
        elif strat == "strangle":
            if args.put_strike is not None and args.call_strike is not None:
                put_k, call_k = args.put_strike, args.call_strike
            else:
                ks = [float(s) for s in args.strikes.split(",") if s]
                if len(ks) != 2:
                    parser.error("strangle requires two strikes")
                put_k, call_k = ks
            ticket = build_strangle(
                args.symbol, args.expiry, float(put_k), float(call_k), qty, args.account
            )
        elif strat == "covered_call":
            call_k = args.call_strike if args.call_strike is not None else None
            if call_k is None and args.strike is not None:
                call_k = float(args.strike)
            if call_k is None and args.strikes:
                call_k = float(args.strikes)
            if call_k is None:
                parser.error("covered_call requires --call-strike")
            ticket = build_covered_call(
                args.symbol, args.expiry, float(call_k), qty, args.account
            )
        else:
            parser.error(f"Unknown strategy {args.strategy}")

    result: Dict[str, Any] = {
        "ok": True,
        "ticket": ticket,
        "outputs": [],
        "warnings": [],
        "meta": {"schema_id": "order_builder", "schema_version": "1"},
    }
    if args.preset:
        result["preset"] = args.preset
    else:
        result["strategy"] = args.strategy
    risk = compute_risk_summary(ticket)
    if risk:
        result["risk_summary"] = risk

    if args.json:
        print(json.dumps(result, separators=(",", ":")))
    if not args.no_files:
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"ticket_{args.symbol}_{ts}"
        io_save(ticket, name, fmt="json")
    return 0


def main(argv: List[str] | None = None) -> int:
    """Console entry wrapper for setuptools scripts."""
    return cli(argv)


if __name__ == "__main__":
    raise SystemExit(cli())
