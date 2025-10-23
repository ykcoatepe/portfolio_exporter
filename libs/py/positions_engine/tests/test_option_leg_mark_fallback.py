# SPDX-License-Identifier: MIT
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from positions_engine.ingest.internal import _synthesize_leg_mark_and_ts


def test_mid_mark_from_bid_ask_with_ts() -> None:
    now = datetime.now(tz=UTC)
    leg = {
        "bid": "1.00",
        "ask": "1.20",
        "bid_ts": (now - timedelta(seconds=30)).isoformat(),
        "ask_ts": (now - timedelta(seconds=25)).isoformat(),
    }
    mark, source, ts = _synthesize_leg_mark_and_ts(leg)
    assert mark == Decimal("1.10")
    assert source == "MID"
    assert ts is not None


def test_last_mark_from_last_with_ts() -> None:
    now = datetime.now(tz=UTC)
    leg = {
        "last": "2.34",
        "quote_timestamp": (now - timedelta(seconds=75)).isoformat(),
    }
    mark, source, ts = _synthesize_leg_mark_and_ts(leg)
    assert mark == Decimal("2.34")
    assert source == "LAST"
    assert ts is not None


def test_prev_mark_from_previous_close_with_ts() -> None:
    now = datetime.now(tz=UTC)
    leg = {
        "previous_close": "0.85",
        "previous_close_ts": (now - timedelta(seconds=15)).isoformat(),
    }
    mark, source, ts = _synthesize_leg_mark_and_ts(leg)
    assert mark == Decimal("0.85")
    assert source == "PREV"
    assert ts is not None


def test_none_when_no_prices_present() -> None:
    mark, source, ts = _synthesize_leg_mark_and_ts({})
    assert mark is None
    assert source is None
    assert ts is None
