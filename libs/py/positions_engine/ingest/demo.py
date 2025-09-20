# SPDX-License-Identifier: MIT

"""Synthetic portfolio dataset used when live data is unavailable."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any


def load_demo_dataset() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return demo positions and quotes with realistic values."""

    now = datetime.now(tz=UTC).replace(microsecond=0)
    expiry = (now + timedelta(days=28)).date().isoformat()
    spy_underlying = "SPY"
    tsla_underlying = "TSLA"
    msft_underlying = "MSFT"

    positions: list[dict[str, Any]] = [
        {
            "symbol": "AAPL",
            "instrument_type": "equity",
            "quantity": 75,
            "avg_cost": 165.25,
            "previous_close": 172.1,
        },
        {
            "symbol": msft_underlying,
            "instrument_type": "equity",
            "quantity": 40,
            "avg_cost": 320.4,
            "previous_close": 327.9,
        },
        {
            "symbol": spy_underlying,
            "instrument_type": "equity",
            "quantity": 30,
            "avg_cost": 425.0,
            "previous_close": 432.6,
        },
        # Iron condor legs on SPY
        {
            "symbol": f"{spy_underlying} {expiry.replace('-', '')}C00440000",
            "instrument_type": "option",
            "underlying": spy_underlying,
            "right": "CALL",
            "strike": 440,
            "expiry": expiry,
            "quantity": 1,
            "avg_cost": 2.05,
            "multiplier": 100,
            "delta": 0.28,
            "theta": -0.04,
        },
        {
            "symbol": f"{spy_underlying} {expiry.replace('-', '')}C00445000",
            "instrument_type": "option",
            "underlying": spy_underlying,
            "right": "CALL",
            "strike": 445,
            "expiry": expiry,
            "quantity": -1,
            "avg_cost": 1.35,
            "multiplier": 100,
            "delta": -0.23,
            "theta": -0.03,
        },
        {
            "symbol": f"{spy_underlying} {expiry.replace('-', '')}P00400000",
            "instrument_type": "option",
            "underlying": spy_underlying,
            "right": "PUT",
            "strike": 400,
            "expiry": expiry,
            "quantity": -1,
            "avg_cost": 1.8,
            "multiplier": 100,
            "delta": -0.21,
            "theta": -0.02,
        },
        {
            "symbol": f"{spy_underlying} {expiry.replace('-', '')}P00395000",
            "instrument_type": "option",
            "underlying": spy_underlying,
            "right": "PUT",
            "strike": 395,
            "expiry": expiry,
            "quantity": 1,
            "avg_cost": 1.1,
            "multiplier": 100,
            "delta": 0.17,
            "theta": -0.015,
        },
        # single option legs
        {
            "symbol": f"{tsla_underlying} {expiry.replace('-', '')}C00750000",
            "instrument_type": "option",
            "underlying": tsla_underlying,
            "right": "CALL",
            "strike": 750,
            "expiry": expiry,
            "quantity": 1,
            "avg_cost": 4.25,
            "multiplier": 100,
            "delta": 0.35,
            "theta": -0.05,
        },
        {
            "symbol": f"{msft_underlying} {expiry.replace('-', '')}P00320000",
            "instrument_type": "option",
            "underlying": msft_underlying,
            "right": "PUT",
            "strike": 320,
            "expiry": expiry,
            "quantity": -1,
            "avg_cost": 2.1,
            "multiplier": 100,
            "delta": -0.32,
            "theta": -0.03,
        },
    ]

    quotes: list[dict[str, Any]] = [
        {
            "symbol": "AAPL",
            "bid": 172.0,
            "ask": 172.1,
            "last": 172.05,
            "previous_close": 171.5,
            "ts": now.isoformat(),
        },
        {
            "symbol": msft_underlying,
            "bid": 328.2,
            "ask": 328.4,
            "last": 328.3,
            "previous_close": 327.9,
            "ts": now.isoformat(),
        },
        {
            "symbol": spy_underlying,
            "bid": 433.0,
            "ask": 433.1,
            "last": 433.05,
            "previous_close": 432.6,
            "ts": now.isoformat(),
        },
    ]

    return positions, quotes
