# SPDX-License-Identifier: MIT

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from positions_engine.service.state import _resolve_option_stale_seconds_entry


def test_staleness_uses_prev_ts_when_available() -> None:
    now = datetime.now(tz=UTC)
    entry = {"kind": "PREV", "prev_ts": (now - timedelta(seconds=123)).isoformat()}

    staleness = _resolve_option_stale_seconds_entry(entry, "PREV", now)
    assert staleness is not None
    assert 120 <= staleness <= 126


def test_staleness_mid_uses_bid_timestamp_fallback() -> None:
    now = datetime.now(tz=UTC)
    entry = {"kind": "MID", "bid_ts": (now - timedelta(seconds=45)).isoformat()}

    staleness = _resolve_option_stale_seconds_entry(entry, "MID", now)
    assert staleness is not None
    assert 42 <= staleness <= 48


def test_staleness_last_uses_quote_timestamp_fallback() -> None:
    now = datetime.now(tz=UTC)
    entry = {
        "kind": "LAST",
        "quote_timestamp": (now - timedelta(seconds=75)).isoformat(),
    }

    staleness = _resolve_option_stale_seconds_entry(entry, "LAST", now)
    assert staleness is not None
    assert 72 <= staleness <= 78


def test_staleness_is_none_when_no_timestamps() -> None:
    now = datetime.now(tz=UTC)

    staleness = _resolve_option_stale_seconds_entry({}, None, now)
    assert staleness is None
