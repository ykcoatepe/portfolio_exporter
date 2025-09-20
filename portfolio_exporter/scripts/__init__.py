"""Scripts package with lazy submodule imports to keep startup fast.

Tests monkey‑patch each script's `run()`; expose submodules on attribute
access so `getattr(scripts, name)` returns the actual module object.
"""

from importlib import import_module
from typing import Any

__all__ = [
    "update_tickers",
    "historic_prices",
    "daily_pulse",
    "option_chain_snapshot",
    "net_liq_history_export",
    "orchestrate_dataset",
    "tech_scan",
    "live_feed",
    "tech_signals_ibkr",
    "portfolio_greeks",
    "risk_watch",
    "theta_cap",
    "gamma_scalp",
    "daily_report",
    "trades_report",
    "order_builder",
    "roll_manager",
    "quick_chain",
    "validate_json",
    "doctor",
    "memory",
]


def __getattr__(name: str) -> Any:  # PEP 562 lazy import
    if name in __all__:
        mod = import_module(f"{__name__}.{name}")
        globals()[name] = mod
        return mod
    raise AttributeError(name)
