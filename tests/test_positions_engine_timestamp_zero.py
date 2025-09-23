from datetime import UTC, datetime

from positions_engine.service.state import (
    _PREV_STALE_FALLBACK_SECONDS,
    _normalize_single_stock,
)


def test_previous_close_zero_timestamp_treated_as_missing() -> None:
    now = datetime(2024, 1, 2, tzinfo=UTC)
    entry = {
        "mark_source": "PREV",
        "previousCloseTs": 0,
    }

    _normalize_single_stock(entry, now)

    assert entry["stale_seconds"] == _PREV_STALE_FALLBACK_SECONDS
    assert entry["stale_s"] == _PREV_STALE_FALLBACK_SECONDS
    assert entry.get("previous_close_ts") not in {"0", "0.0"}


def test_previous_close_zero_string_variants_treated_as_missing() -> None:
    now = datetime(2024, 1, 2, tzinfo=UTC)
    zero_variants = (
        "0",
        " 0 ",
        "0.0",
        "0.000",
        "+0",
        "-0",
        "000",
        "0e0",
        "0E-3",
        ".0",
    )

    for value in zero_variants:
        for key in ("previous_close_ts", "previousCloseTs"):
            entry = {
                "mark_source": "PREV",
                key: value,
            }

            _normalize_single_stock(entry, now)

            assert entry["stale_seconds"] == _PREV_STALE_FALLBACK_SECONDS
            assert entry["stale_s"] == _PREV_STALE_FALLBACK_SECONDS
