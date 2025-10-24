"""Shared datasource helpers for the Portfolio Sentinel Dashboard."""

from __future__ import annotations

import os
from collections.abc import Mapping

_VALID_SOURCES = {"vendor", "fred", "ibkr", "yf"}
_TRUTHY = {"1", "true", "yes", "on"}


def resolve_msb_source(env: Mapping[str, str] | None = None) -> str:
    """Return the configured MSB datasource selection.

    Accepts ``fred`` (FRED API), ``ibkr`` (Interactive Brokers), ``yf`` (Yahoo
    Finance) and ``vendor`` (default local CSV snapshot). Unknown values fall
    back to ``vendor`` to preserve the existing behaviour.
    """

    env_map = env or os.environ
    raw = str(env_map.get("MSB_SOURCE", "")).strip().lower()
    if raw in _VALID_SOURCES:
        return raw
    return "vendor"


def is_offline(env: Mapping[str, str] | None = None) -> bool:
    """Heuristic check for offline/test modes.

    Several parts of the toolchain set ``PE_TEST_MODE`` or ``MOMO_OFFLINE``
    during CI. Treat any of these truthy flags as an instruction to avoid
    network IO.
    """

    env_map = env or os.environ
    for key in ("MOMO_OFFLINE", "PE_TEST_MODE", "PSD_OFFLINE"):
        value = env_map.get(key)
        if value is None:
            continue
        if str(value).strip().lower() in _TRUTHY:
            return True
    return False


__all__ = ["resolve_msb_source", "is_offline"]
