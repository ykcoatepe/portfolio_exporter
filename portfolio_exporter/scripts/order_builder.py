"""
order_builder.py – Interactive ticket wizard for simple strategies
Currently supports:
  • Covered call
  • Cash-secured put
  • Vertical spread (call or put)
"""

import builtins
import datetime
import json
import pathlib

from prompt_toolkit import prompt

from portfolio_exporter.core.config import settings
from portfolio_exporter.core.input import parse_order_line

# Expose prompt_toolkit.prompt via a dotted builtins attribute for tests
setattr(builtins, "prompt_toolkit.prompt", prompt)


def _ask(question, default=None):
    default_str = f" [{default}]" if default else ""
    ask_fn = getattr(builtins, "prompt_toolkit.prompt", prompt)
    return ask_fn(f"{question}{default_str}: ") or default


def run():
    raw = input("Order (shorthand, Enter to step-through): ").strip()
    parsed = parse_order_line(raw) if raw else None

    today = datetime.date.today()
    expiry_default = (today + datetime.timedelta(weeks=2)).isoformat()
    strat_default = "cc"
    underlying_default = "TSLA"
    qty_default = "1"
    strikes_default = ""
    right = None

    if parsed:
        underlying_default = parsed.underlying
        expiry_default = parsed.legs[0].expiry.isoformat()
        qty_default = str(parsed.qty)
        strikes_default = ",".join(f"{leg.strike:g}" for leg in parsed.legs)
        right = parsed.legs[0].right
        strat_default = (
            "vert" if len(parsed.legs) == 2 else ("csp" if right == "P" else "cc")
        )

    strat = _ask("Strategy (cc/csp/vert)", strat_default).lower()
    underlying = _ask("Underlying", underlying_default).upper()
    expiry = _ask("Expiry (YYYY-MM-DD)", expiry_default)
    qty = int(_ask("Contracts", qty_default))
    strikes_in = _ask("Strike(s) (comma-sep)", strikes_default).replace(" ", "")
    strikes = [float(s) for s in strikes_in.split(",") if s]
    if not right:
        right = "P" if strat == "csp" else "C"

    ticket = {
        "strategy": strat,
        "underlying": underlying,
        "expiry": expiry,
        "qty": qty,
        "strikes": strikes,
        "right": right,
        "account": settings.default_account,
    }

    # Save ticket to JSON in output_dir
    out = pathlib.Path(settings.output_dir).expanduser() / "tickets"
    out.mkdir(parents=True, exist_ok=True)
    fn = (
        out
        / f"ticket_{underlying}_{expiry}_{datetime.datetime.now().strftime('%H%M%S')}.json"
    )
    fn.write_text(json.dumps(ticket, indent=2))
    print(f"✅ Ticket saved to {fn}")
