import json
from portfolio_exporter.scripts.order_builder import (
    build_vertical,
    build_iron_condor,
    build_butterfly,
    build_calendar,
    build_straddle,
    build_strangle,
    build_covered_call,
)


def _leg_map(ticket):
    return [(leg.get("right", ""), leg.get("strike"), leg["qty"], leg.get("expiry")) for leg in ticket["legs"]]


def test_vertical_calls_qty_flip():
    t = build_vertical("XYZ", "2025-01-17", "C", [100, 110], 1, "acc")
    assert _leg_map(t) == [("C", 100, 1, "2025-01-17"), ("C", 110, -1, "2025-01-17")]
    t2 = build_vertical("XYZ", "2025-01-17", "C", [110, 100], -1, "acc")
    assert _leg_map(t2) == [("C", 100, -1, "2025-01-17"), ("C", 110, 1, "2025-01-17")]


def test_vertical_puts_qty_flip():
    t = build_vertical("XYZ", "2025-01-17", "P", [90, 100], 1, "acc")
    assert _leg_map(t) == [("P", 100, -1, "2025-01-17"), ("P", 90, 1, "2025-01-17")]
    t2 = build_vertical("XYZ", "2025-01-17", "P", [100, 90], -1, "acc")
    assert _leg_map(t2) == [("P", 100, 1, "2025-01-17"), ("P", 90, -1, "2025-01-17")]


def test_iron_condor_orientation():
    t = build_iron_condor("XYZ", "2025-01-17", [95, 90, 105, 110], -1, "acc")
    assert _leg_map(t) == [
        ("P", 95, -1, "2025-01-17"),
        ("P", 90, 1, "2025-01-17"),
        ("C", 105, -1, "2025-01-17"),
        ("C", 110, 1, "2025-01-17"),
    ]
    t2 = build_iron_condor("XYZ", "2025-01-17", [90, 95, 105, 110], 1, "acc")
    assert _leg_map(t2) == [
        ("P", 95, 1, "2025-01-17"),
        ("P", 90, -1, "2025-01-17"),
        ("C", 105, 1, "2025-01-17"),
        ("C", 110, -1, "2025-01-17"),
    ]


def test_butterfly_ratio():
    t = build_butterfly("XYZ", "2025-01-17", "C", [90, 100, 110], 1, "acc")
    assert _leg_map(t) == [
        ("C", 90, 1, "2025-01-17"),
        ("C", 100, -2, "2025-01-17"),
        ("C", 110, 1, "2025-01-17"),
    ]
    t2 = build_butterfly("XYZ", "2025-01-17", "P", [90, 100, 110], -1, "acc")
    assert _leg_map(t2) == [
        ("P", 90, -1, "2025-01-17"),
        ("P", 100, 2, "2025-01-17"),
        ("P", 110, -1, "2025-01-17"),
    ]


def test_calendar_flip():
    t = build_calendar(
        "XYZ",
        "2025-02-21",
        "C",
        "2025-01-17",
        "2025-02-21",
        100,
        1,
        "acc",
    )
    assert _leg_map(t) == [
        ("C", 100, -1, "2025-01-17"),
        ("C", 100, 1, "2025-02-21"),
    ]
    t2 = build_calendar(
        "XYZ",
        "2025-02-21",
        "P",
        "2025-01-17",
        "2025-02-21",
        100,
        -1,
        "acc",
    )
    assert _leg_map(t2) == [
        ("P", 100, 1, "2025-01-17"),
        ("P", 100, -1, "2025-02-21"),
    ]


def test_straddle_and_strangle():
    t = build_straddle("XYZ", "2025-01-17", 100, 1, "acc")
    assert _leg_map(t) == [
        ("C", 100, 1, "2025-01-17"),
        ("P", 100, 1, "2025-01-17"),
    ]
    t2 = build_strangle("XYZ", "2025-01-17", 90, 110, -1, "acc")
    assert _leg_map(t2) == [
        ("P", 90, -1, "2025-01-17"),
        ("C", 110, -1, "2025-01-17"),
    ]


def test_covered_call_signs():
    t = build_covered_call("XYZ", "2025-01-17", 105, -2, "acc")
    assert _leg_map(t) == [("C", 105, -2, "2025-01-17"), ("", None, 200, None)]
    t2 = build_covered_call("XYZ", "2025-01-17", 105, 1, "acc")
    assert _leg_map(t2) == [("C", 105, -1, "2025-01-17"), ("", None, 100, None)]
