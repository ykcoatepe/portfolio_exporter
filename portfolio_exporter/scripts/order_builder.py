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

# Expose prompt_toolkit.prompt via a dotted builtins attribute for tests
setattr(builtins, "prompt_toolkit.prompt", prompt)


def _ask(question, default=None):
    default_str = f" [{default}]" if default else ""
    ask_fn = getattr(builtins, "prompt_toolkit.prompt", prompt)
    return ask_fn(f"{question}{default_str}: ") or default


def run():
    strat = _ask("Strategy (cc/csp/vert)", "cc").lower()
    underlying = _ask("Underlying", "TSLA").upper()
    expiry = _ask(
        "Expiry (YYYY-MM-DD)",
        (datetime.date.today() + datetime.timedelta(weeks=2)).isoformat(),
    )
    qty = int(_ask("Contracts", "1"))
    strikes = _ask("Strike(s) (comma-sep)").replace(" ", "")
    strikes = [float(s) for s in strikes.split(",")]

    ticket = {
        "strategy": strat,
        "underlying": underlying,
        "expiry": expiry,
        "qty": qty,
        "strikes": strikes,
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
