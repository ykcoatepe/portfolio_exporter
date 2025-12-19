"""IBKR connection configuration and client id helper.

This thin module centralizes how scripts derive the Interactive Brokers
connection parameters and per-script client IDs. It intentionally has
no heavy imports to keep CLI startup fast.

Environment variables
---------------------
- `IB_HOST`: IBKR host (default: `127.0.0.1`).
- `IB_PORT`: IBKR port. If unset, scripts try Gateway (4001) then TWS (7496).
  Set explicitly to disable fallback or for paper trading (4002/7497).
- `IB_CLIENT_ID`: Fallback client id if a per-script one is not provided.
- `IB_CLIENT_ID_<NAME>`: Per-script client id override, where `<NAME>` is the
  uppercased name passed to `client_id(name, default)` (e.g., `update_tickers`
  -> `IB_CLIENT_ID_UPDATE_TICKERS`).

The `client_id` helper returns a stable integer that callers can use when
connecting via `ib_insync`. Callers typically pass a human-friendly name and a
default value that avoids collisions across concurrently running tools.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ib_insync import IB

log = logging.getLogger(__name__)

# Port constants
_GATEWAY_LIVE = 4001
_TWS_LIVE = 7496


def _safe_parse_port(default: int = _GATEWAY_LIVE) -> int:
    """Safely parse IB_PORT with fallback for empty/invalid values."""

    raw = os.getenv("IB_PORT", "")
    if not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        log.warning("Invalid IB_PORT=%r, using default %d", raw, default)
        return default


# Defaults: Gateway live (4001). Silent fallback to TWS (7496) when IB_PORT unset.
HOST: str = os.getenv("IB_HOST", "127.0.0.1")
PORT: int = _safe_parse_port(_GATEWAY_LIVE)


def is_port_explicit() -> bool:
    """Return True if IB_PORT was explicitly set in the environment.

    Computed at call-time so env changes after import are respected.
    """

    return "IB_PORT" in os.environ


def connect_ports() -> tuple[int, ...]:
    """Return ordered port tuple for connection attempts.

    - When IB_PORT is set -> returns (PORT,), no fallback.
    - When IB_PORT is unset -> returns (4001, 7496) for silent fallback.
    """

    if is_port_explicit():
        return (_safe_parse_port(),)
    return (_GATEWAY_LIVE, _TWS_LIVE)


_last_good_port: int | None = None


def connect_ib(
    ib: "IB",
    *,
    host: str | None = None,
    port: int | None = None,
    client_id: int = 0,
    timeout: int = 10,
    silent_first: bool = True,
) -> int:
    """Connect to IBKR with optional Gateway-to-TWS fallback.

    Args:
        ib: ib_insync.IB instance to connect.
        host: Override IB_HOST (default: use HOST from env).
        port: Explicit port to use. If provided, no fallback occurs.
        client_id: Client ID for this connection.
        timeout: Connection timeout in seconds.
        silent_first: If True, log first port failure at DEBUG level.

    Returns:
        The port that succeeded.

    Raises:
        ConnectionError: if all ports fail.
    """

    global _last_good_port

    target_host = host if host is not None else HOST

    if port is not None:
        ports = (port,)
    else:
        ports = connect_ports()
        if (
            _last_good_port
            and _last_good_port in ports
            and _last_good_port != ports[0]
        ):
            ports = (_last_good_port,) + tuple(p for p in ports if p != _last_good_port)

    last_exc: Exception | None = None
    for idx, try_port in enumerate(ports):
        try:
            ib.connect(target_host, try_port, clientId=client_id, timeout=timeout)
            if idx > 0:
                log.info("Connected to IBKR on fallback port %d", try_port)
            else:
                log.debug("Connected to IBKR on port %d", try_port)
            _last_good_port = try_port
            return try_port
        except Exception as exc:
            last_exc = exc
            if silent_first and idx == 0 and len(ports) > 1:
                log.debug("Port %d unreachable, trying fallback...", try_port)
            else:
                log.warning("Port %d unreachable: %s", try_port, exc)

    raise ConnectionError(
        f"Could not connect to IBKR at {target_host}. Tried ports: {ports}"
    ) from last_exc


def client_id(name: str, default: int = 0) -> int:
    """Return the IB client id for a given logical name.

    Resolution order:
    1) `IB_CLIENT_ID_<NAME>` (NAME uppercased, non-alphanumeric -> underscore)
    2) `IB_CLIENT_ID`
    3) provided `default`
    """

    token = "".join(ch if ch.isalnum() else "_" for ch in name).upper()
    per_name = os.getenv(f"IB_CLIENT_ID_{token}")
    if per_name and per_name.strip():
        try:
            return int(per_name)
        except ValueError:
            pass

    generic = os.getenv("IB_CLIENT_ID")
    if generic and generic.strip():
        try:
            return int(generic)
        except ValueError:
            pass

    return int(default)


__all__ = [
    "HOST",
    "PORT",
    "client_id",
    "is_port_explicit",
    "connect_ports",
    "connect_ib",
]
