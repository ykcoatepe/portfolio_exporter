"""order_builder.py – Interactive ticket wizard for simple strategies."""

from __future__ import annotations

import builtins
import datetime as dt
import datetime as _dt
import json
import pathlib
from typing import Any, Dict, List, Optional, Tuple

from prompt_toolkit import prompt
from yfinance import Ticker

from portfolio_exporter.core.config import settings
from portfolio_exporter.core.input import parse_order_line
from portfolio_exporter.core.ui import banner_delta_theta, console
from rich.table import Table
try:  # pragma: no cover - ib_insync optional in tests
    from portfolio_exporter.core.ib import quote_option, quote_stock  # type: ignore
except Exception:  # pragma: no cover
    quote_option = quote_stock = None  # type: ignore

# Expose prompt_toolkit.prompt via a dotted builtins attribute for tests
setattr(builtins, "prompt_toolkit.prompt", prompt)

# ── expiry normaliser ---------------------------------------------------------
_expiry_cache: dict[str, list[str]] = {}


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
    d = _parse_date_like(str(raw))
    if not d:
        d = _nearest_friday(_dt.date.today() + _dt.timedelta(weeks=2))
    return d.isoformat()


def _ask(question: str, default: Optional[str] = None) -> str | None:
    default_str = f" [{default}]" if default else ""
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
):
    k_low, k_high = sorted(strikes)
    ticket = _base_ticket("vertical", symbol, expiry, qty, [k_low, k_high], right, account)
    if right == "C":
        legs = [
            {"secType": "OPT", "right": "C", "strike": k_low, "qty": qty, "expiry": expiry},
            {"secType": "OPT", "right": "C", "strike": k_high, "qty": -qty, "expiry": expiry},
        ]
    else:  # Puts
        legs = [
            {"secType": "OPT", "right": "P", "strike": k_high, "qty": -qty, "expiry": expiry},
            {"secType": "OPT", "right": "P", "strike": k_low, "qty": qty, "expiry": expiry},
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


def run() -> bool:
    raw = input("Order (shorthand, Enter to step-through): ").strip()
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
        expiry_in = _ask("Expiry (YYYY-MM-DD)", expiry_default) or expiry_default
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
        # Strategy-specific strikes collection
        if strat in {"cc", "csp", "vert"}:
            strikes_in = (
                _ask("Strike(s) (comma-sep)", strikes_default) or ""
            ).replace(" ", "")
            strikes = [float(s) for s in strikes_in.split(",") if s]
        elif strat in {"ic", "iron_condor"}:
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
            # strike gathered later as single float
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
        r = (_ask("Right (C/P)", "C") or "C").upper()
        near_in = _ask("Near expiry (YYYY-MM-DD)", expiry) or expiry
        far_in = _ask("Far expiry (YYYY-MM-DD)", expiry) or expiry
        near = _normalize_expiry(underlying, near_in)
        far = _normalize_expiry(underlying, far_in)
        if not strikes:
            raise ValueError("Calendar requires a strike")
        strike = float(strikes[0])
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
        risk_caps_ok = input("Proceed? (y/N): ").strip().lower() == "y"
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
    from portfolio_exporter.core.io import save as io_save

    parser = argparse.ArgumentParser(description="Build option strategy tickets")
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--expiry", default="")
    parser.add_argument("--expiry-near", dest="expiry_near", default=None)
    parser.add_argument("--expiry-far", dest="expiry_far", default=None)
    parser.add_argument("--right", default="")
    parser.add_argument("--strikes", default="")
    parser.add_argument("--strike", type=float, default=None)
    parser.add_argument("--put-strike", dest="put_strike", type=float, default=None)
    parser.add_argument("--call-strike", dest="call_strike", type=float, default=None)
    parser.add_argument("--qty", type=int, default=1)
    parser.add_argument("--account", default=None)
    parser.add_argument("--json", action="store_true", help="Print ticket JSON to stdout and do not write files")
    args = parser.parse_args(argv)

    strat = args.strategy.lower().replace("-", "_")
    qty = int(args.qty)
    ticket: Dict[str, Any]

    if strat == "vertical":
        strikes = [float(s) for s in args.strikes.split(",") if s]
        ticket = build_vertical(
            args.symbol, args.expiry, args.right.upper(), strikes, qty, args.account
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

    if args.json:
        print(json.dumps(ticket, separators=(",", ":")))
        return 0
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"ticket_{args.symbol}_{ts}"
    io_save(ticket, name, fmt="json")
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
