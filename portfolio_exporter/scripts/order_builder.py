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
from portfolio_exporter.core.ib import quote_option, quote_stock

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
        expiry = _nearest_expiry(symbol, expiry) if expiry else expiry
        return quote_option(symbol, expiry or "", float(strike), right)
    data = quote_stock(symbol)
    data.update({"delta": 1.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "iv": 0.0})
    return data


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

    if parsed and len(parsed.legs) == 2:
        strat = "vert"
    else:
        strat = (_ask("Strategy (cc/csp/vert)", strat_default) or "cc").lower()

    if parsed and len(parsed.legs) == 2:
        underlying = underlying_default
    else:
        underlying = (_ask("Underlying", underlying_default) or "TSLA").upper()

    if parsed:
        expiry = expiry_default
    else:
        expiry = _ask("Expiry (YYYY-MM-DD)", expiry_default) or expiry_default

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
