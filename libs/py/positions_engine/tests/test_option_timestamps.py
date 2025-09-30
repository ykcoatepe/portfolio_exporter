# SPDX-License-Identifier: MIT

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from positions_engine.service.state import _normalize_option_leg_entry


def test_mid_alias_bid_ask_timestamps_drive_staleness() -> None:
    now = datetime(2024, 1, 3, 15, 0, tzinfo=UTC)
    bid_alias = (now - timedelta(seconds=45)).isoformat()
    ask_alias = (now - timedelta(seconds=30)).isoformat()
    leg = {
        "mark_source": "MID",
        "bid_timestamp": f"  {bid_alias}  ",
        "askTimestamp": ask_alias,
    }

    _normalize_option_leg_entry(leg, now)

    assert leg["bid_ts"] == bid_alias
    assert leg["ask_ts"] == ask_alias
    assert leg["stale_seconds"] == 30
    assert leg["stale_s"] == 30


def test_last_alias_timestamp_sets_staleness() -> None:
    now = datetime(2024, 1, 3, 15, 0, tzinfo=UTC)
    last_alias = (now - timedelta(seconds=50)).isoformat()
    leg = {
        "mark_source": "LAST",
        "lastTradeTimestamp": last_alias,
    }

    _normalize_option_leg_entry(leg, now)

    assert leg["last_ts"] == last_alias
    assert leg["stale_seconds"] == 50
    assert leg["stale_s"] == 50


def test_previous_close_alias_timestamp_sets_staleness() -> None:
    now = datetime(2024, 1, 3, 15, 0, tzinfo=UTC)
    prev_alias = (now - timedelta(hours=18)).isoformat()
    leg = {
        "mark_source": "PREV",
        "previousCloseTimestamp": prev_alias,
    }

    _normalize_option_leg_entry(leg, now)

    assert leg["previous_close_ts"] == prev_alias
    expected = int((now - datetime.fromisoformat(prev_alias)).total_seconds())
    assert leg["stale_seconds"] == expected
    assert leg["stale_s"] == expected


def test_missing_timestamps_fall_back_to_conservative_age() -> None:
    now = datetime(2024, 1, 3, 15, 0, tzinfo=UTC)
    leg = {"mark_source": "MID"}

    _normalize_option_leg_entry(leg, now)

    assert "stale_seconds" not in leg
    assert "stale_s" not in leg


def test_mid_option_falls_back_to_updated_at_when_no_alias() -> None:
    now = datetime(2024, 1, 3, 15, 0, tzinfo=UTC)
    updated = (now - timedelta(seconds=75)).isoformat()
    leg = {
        "mark_source": "MID",
        "updated_at": updated,
    }

    _normalize_option_leg_entry(leg, now)

    assert leg["stale_seconds"] == 75
    assert leg["stale_s"] == 75


def test_zero_canonical_timestamp_replaced_by_alias() -> None:
    now = datetime(2024, 1, 3, 15, 0, tzinfo=UTC)
    bid_alias = (now - timedelta(seconds=90)).isoformat()
    leg = {
        "mark_source": "MID",
        "bid_ts": "0",
        "bidTimestamp": bid_alias,
    }

    _normalize_option_leg_entry(leg, now)

    assert leg["bid_ts"] == bid_alias
    assert leg["stale_seconds"] == 90
    assert leg["stale_s"] == 90
