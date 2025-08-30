"""Menus package with lazy submodule imports.

Avoid importing heavy dependencies at package import time. Submodules are
loaded on first access or when explicitly imported, e.g.::

    from portfolio_exporter.menus import trade

This keeps `yfinance` and other optional deps out of the import path unless
the corresponding menu is used.
"""

from importlib import import_module
from typing import Any

__all__ = ["pre", "live", "trade"]


def __getattr__(name: str) -> Any:  # PEP 562 lazy import
    if name in __all__:
        mod = import_module(f"{__name__}.{name}")
        globals()[name] = mod
        return mod
    raise AttributeError(name)
