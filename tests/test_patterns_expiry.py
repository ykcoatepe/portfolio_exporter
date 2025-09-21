from __future__ import annotations

from datetime import date, timedelta

from portfolio_exporter.core.patterns import compute_patterns
from portfolio_exporter.core.micro_momo_optionpicker import _pick_expiry_by_dte, _dte


def _bar(c: float, h: float | None = None, l: float | None = None, v: int = 1000):
    return {
        "open": c,
        "high": h if h is not None else c,
        "low": l if l is not None else c,
        "close": c,
        "volume": v,
    }


def test_patterns_vwap_reclaim():
    # First 5 bars mostly below final VWAP; ORB high set high to avoid ORB detection
    bars = [
        _bar(100.0, h=106.0),
        _bar(100.2, h=105.0),
        _bar(99.8, h=104.0),
        _bar(100.1, h=103.0),
        _bar(100.0, h=102.0),
        _bar(101.5),
        _bar(102.0),
        _bar(103.0),
        _bar(103.5),
        _bar(104.0),
        _bar(104.5),
    ]
    out = compute_patterns(bars)
    assert out["pattern_signal"] == "VWAP Reclaim"
    assert out["above_vwap_now"] in {"Yes", "No"}
    assert out["vwap"] is not None


def test_patterns_orb_break_and_retest():
    # ORB: first 5 bars set orb_high around 100, then break, retest, and re-break
    bars = [
        _bar(99.5, h=100.0),
        _bar(99.8, h=100.2),
        _bar(99.9, h=100.1),
        _bar(99.7, h=100.0),
        _bar(99.6, h=100.0),
        _bar(100.3),  # initial break > orb_high ≈ 100.2
        _bar(100.2),  # retest within 0.15%
        _bar(100.5),  # re-break
    ]
    out = compute_patterns(bars)
    assert out["pattern_signal"] == "ORB Retest"


def test_patterns_hod_reclaim():
    # Set an early spike high to keep ORB high above current closes; then HOD reclaim vs prior HOD
    bars = [
        _bar(100.0, h=110.0),  # early spike keeps ORB high above
        _bar(101.0, h=101.5),
        _bar(102.0, h=102.5),
        _bar(103.0, h=103.2),
        _bar(103.5, h=103.7),
        _bar(104.0, h=104.0),
        _bar(104.5, h=104.6),  # slight higher high
        _bar(104.2, h=104.2),  # dip breaks "rising tail"
        _bar(105.1, h=105.2),  # reclaim recent HOD without ORB
    ]
    out = compute_patterns(bars)
    assert out["pattern_signal"] == "HOD Reclaim"


def test_expiry_picker_in_window_prefers_oi():
    today = date(2025, 1, 10)
    spot = 100.0

    def yyyymmdd(d: date) -> str:
        return d.strftime("%Y%m%d")

    e_low_oi = yyyymmdd(today + timedelta(days=5))
    e_high_oi = yyyymmdd(today + timedelta(days=6))
    # Chain rows around spot with different OI per expiry
    chain = []
    for e, oi in ((e_low_oi, 100), (e_high_oi, 500)):
        for k in range(-2, 3):
            strike = spot * (1 + k * 0.01)
            chain.append({"symbol": "TEST", "expiry": e, "right": "C", "strike": strike, "bid": 1.0, "ask": 1.2, "last": 1.1, "volume": 0, "oi": oi})
            chain.append({"symbol": "TEST", "expiry": e, "right": "P", "strike": strike, "bid": 1.0, "ask": 1.2, "last": 1.1, "volume": 0, "oi": oi})

    picked = _pick_expiry_by_dte(chain, spot, dte_min=3, dte_max=10, today=today)
    assert picked == e_high_oi


def test_expiry_picker_weekly_above_max():
    today = date(2025, 1, 10)  # Friday
    spot = 100.0

    def yyyymmdd(d: date) -> str:
        return d.strftime("%Y%m%d")

    # No in-window expiries; one just above max and on Friday
    dte_min, dte_max = 3, 7
    e1 = yyyymmdd(today + timedelta(days=2))  # below min
    e2 = yyyymmdd(today + timedelta(days=10))  # above max by 3 (prefer, and it's a Monday 2025-01-20)
    # Ensure a Friday within +7: next Friday after dte_max
    e_friday = yyyymmdd(today + timedelta(days=7))  # exact +7 and Friday 2025-01-17

    chain = []
    for e in (e1, e2, e_friday):
        for k in range(-2, 3):
            strike = spot * (1 + k * 0.01)
            chain.append({"symbol": "TEST", "expiry": e, "right": "C", "strike": strike, "bid": 1.0, "ask": 1.2, "last": 1.1, "volume": 0, "oi": 100})

    picked = _pick_expiry_by_dte(chain, spot, dte_min=dte_min, dte_max=dte_max, today=today)
    # Prefer the Friday within +7 days above max (e_friday)
    assert picked == e_friday


def test_dte_basic():
    today = date(2025, 1, 10)
    assert _dte("20250110", today) == 0
    assert _dte("20250111", today) == 1
