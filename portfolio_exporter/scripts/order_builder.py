"""order_builder.py – Interactive ticket wizard for simple strategies."""

from __future__ import annotations

import builtins
import datetime as dt
import datetime as _dt
import json
import pathlib
from typing import Any, Dict, List, Optional

from prompt_toolkit import prompt
from yfinance import Ticker

from portfolio_exporter.core.config import settings
from portfolio_exporter.core.input import parse_order_line
from portfolio_exporter.core.ui import banner_delta_theta, console
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


def _ask(question: str, default: Optional[str] = None) -> str | None:
    default_str = f" [{default}]" if default else ""
    ask_fn = getattr(builtins, "prompt_toolkit.prompt", prompt)
    return ask_fn(f"{question}{default_str}: ") or default


def _price_leg(
    symbol: str, expiry: str | None, strike: float | None, right: str | None
) -> Dict[str, float]:
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
    data.update({"delta": 1.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "iv": 0.0})
    return data


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
    underlying_default = "TSLA"
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
            strat = (_ask("Strategy (cc/csp/vert)", strat_default) or "cc").lower()

    # ------------------------------------------------------------------
    # 2) UNDERLYING
    # ------------------------------------------------------------------
    if parsed and len(parsed.legs) == 2:
        underlying = underlying_default
    else:
        if have_all_fields:
            underlying = underlying_default
        else:
            underlying = (_ask("Underlying", underlying_default) or "TSLA").upper()

    # ------------------------------------------------------------------
    # 3) EXPIRY
    # ------------------------------------------------------------------
    if parsed:
        expiry = expiry_default
    else:
        expiry = _ask("Expiry (YYYY-MM-DD)", expiry_default) or expiry_default

    # ------------------------------------------------------------------
    # 4) QTY & STRIKES
    # ------------------------------------------------------------------
    if parsed:
        qty = int(qty_default)
        strikes = [leg.strike for leg in parsed.legs]
    else:
        qty = int(_ask("Contracts", qty_default) or qty_default)
        strikes_in = (_ask("Strike(s) (comma-sep)", strikes_default) or "").replace(
            " ", ""
        )
        strikes = [float(s) for s in strikes_in.split(",") if s]

    if not right:
        right = "P" if strat == "csp" else "C"

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
        if right == "C":
            legs.append(
                {
                    "symbol": underlying,
                    "expiry": expiry,
                    "strike": strikes[0],
                    "right": right,
                    "qty": qty,
                    "mult": 100,
                }
            )
            legs.append(
                {
                    "symbol": underlying,
                    "expiry": expiry,
                    "strike": strikes[1],
                    "right": right,
                    "qty": -qty,
                    "mult": 100,
                }
            )
        else:
            legs.append(
                {
                    "symbol": underlying,
                    "expiry": expiry,
                    "strike": strikes[0],
                    "right": right,
                    "qty": -qty,
                    "mult": 100,
                }
            )
            legs.append(
                {
                    "symbol": underlying,
                    "expiry": expiry,
                    "strike": strikes[1],
                    "right": right,
                    "qty": qty,
                    "mult": 100,
                }
            )
    else:
        raise ValueError(f"Unknown strategy {strat}")

    cfg = getattr(settings, "order_builder", None)
    slippage = getattr(cfg, "slippage", 0.05)
    delta_cap = getattr(cfg, "delta_cap", float("inf"))
    theta_cap = getattr(cfg, "theta_cap", float("-inf"))
    confirm_caps = getattr(cfg, "confirm_above_caps", True)

    mid_prices: List[float] = []
    net_mid = net_delta = net_theta = net_gamma = net_vega = 0.0
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
        rows.append(
            {
                "underlying": underlying,
                "strategy": strat,
                "expiry": leg.get("expiry") or "",
                "strike": leg.get("strike") or "",
                "right": leg.get("right") or "",
                "qty": leg_qty,
                "mid": price["mid"],
                "delta": price["delta"],
                "theta": price["theta"],
                "vega": price["vega"],
                "iv": price["iv"],
            }
        )

    rows.append(
        {
            "underlying": "TOTAL",
            "strategy": "",
            "expiry": "",
            "strike": "",
            "right": "",
            "qty": sum(leg["qty"] for leg in legs),
            "mid": net_mid,
            "delta": net_delta,
            "theta": net_theta,
            "vega": net_vega,
            "iv": "",
        }
    )

    outdir = pathlib.Path(settings.output_dir).expanduser()
    outdir.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    preview_path = outdir / f"order_preview_{ts}.csv"
    import pandas as pd

    pd.DataFrame(rows).to_csv(preview_path, index=False)

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

    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"ticket_{args.symbol}_{ts}"
    io_save(ticket, name, fmt="json")
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
