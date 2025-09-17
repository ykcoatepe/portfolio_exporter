"""IBKR connection configuration and client id helper.

This thin module centralizes how scripts derive the Interactive Brokers
connection parameters and per-script client IDs. It intentionally has
no heavy imports to keep CLI startup fast.

Environment variables
---------------------
- `IB_HOST`: IBKR host (default: `127.0.0.1`).
- `IB_PORT`: IBKR port (default: `7496`).
- `IB_CLIENT_ID`: Fallback client id if a per-script one isn’t provided.
- `IB_CLIENT_ID_<NAME>`: Per-script client id override, where `<NAME>` is the
  uppercased name passed to `client_id(name, default)` (e.g., `update_tickers`
  → `IB_CLIENT_ID_UPDATE_TICKERS`).

The `client_id` helper returns a stable integer that callers can use when
connecting via `ib_insync`. Callers typically pass a human-friendly name and a
default value that avoids collisions across concurrently running tools.
"""

from __future__ import annotations

import os

# Defaults align with a typical TWS live setup (set IB_PORT=7497 for paper).
HOST: str = os.getenv("IB_HOST", "127.0.0.1")
PORT: int = int(os.getenv("IB_PORT", "7496"))


def client_id(name: str, default: int = 0) -> int:
    """Return the IB client id for a given logical name.

    Resolution order:
    1) `IB_CLIENT_ID_<NAME>` (NAME uppercased, non-alphanumeric → underscore)
    2) `IB_CLIENT_ID`
    3) provided `default`
    """

    # Normalize to env var friendly token
    token = "".join(ch if ch.isalnum() else "_" for ch in name).upper()
    per_name = os.getenv(f"IB_CLIENT_ID_{token}")
    if per_name and per_name.strip():
        try:
            return int(per_name)
        except ValueError:
            pass  # fall through to generic/default

    generic = os.getenv("IB_CLIENT_ID")
    if generic and generic.strip():
        try:
            return int(generic)
        except ValueError:
            pass

    return int(default)


__all__ = ["HOST", "PORT", "client_id"]

