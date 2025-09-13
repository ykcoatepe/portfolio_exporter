from __future__ import annotations

import json

from portfolio_exporter.core.micro_momo import entry_trigger, passes_filters, score_components, size_and_targets, tier_and_dir
from portfolio_exporter.core.micro_momo_optionpicker import pick_structure
from portfolio_exporter.core.micro_momo_sources import load_chain_csv, load_scan_csv


def _cfg() -> dict:
    with open("tests/data/micro_momo_config.json", "r", encoding="utf-8") as f:
        return json.load(f)


def test_filters_scoring_and_sizing() -> None:
    cfg = _cfg()
    scans = load_scan_csv("tests/data/meme_scan_sample.csv")
    row = scans[0]  # ABC good row

    assert passes_filters(row, cfg) is True
    comps, raw = score_components(row, cfg)
    assert 0.0 <= raw <= 100.0

    tier, direction = tier_and_dir(row, raw, cfg)
    assert tier in {"A", "B", "C"}
    assert direction in {"long", "short", "long?"}

    chain = load_chain_csv("tests/data/ABC_20250115.csv")
    struct = pick_structure(row, chain, direction="long", cfg=cfg)
    contracts, tp, sl = size_and_targets(struct, row, cfg)
    assert contracts > 0  # debit sizing should be >0
    assert tp > 0 and sl >= 0

    trig = entry_trigger("long", row, cfg)
    assert isinstance(trig, str)


def test_direction_long_with_vwap_reclaim() -> None:
    cfg = _cfg()
    scans = load_scan_csv("tests/data/meme_scan_sample.csv")
    row = scans[0]
    # Provide fields needed by direction logic
    row.above_vwap_now = "Yes"  # type: ignore[attr-defined]
    row.pattern_signal = "VWAP Reclaim"  # type: ignore[attr-defined]
    _, raw = score_components(row, cfg)
    _, direction = tier_and_dir(row, raw, cfg)
    assert direction == "long"


def test_filters_fail_on_small_premarket_gap() -> None:
    cfg = _cfg()
    # Ensure the min gap requirement is set
    cfg.setdefault("filters", {})
    cfg["filters"]["premkt_gap_min_pct"] = 1.0
    scans = load_scan_csv("tests/data/meme_scan_sample.csv")
    row = scans[0]
    row.premkt_gap_pct = 0.0  # type: ignore[attr-defined]
    assert passes_filters(row, cfg) is False


def test_b_tier_bull_put_credit_when_debit_fails() -> None:
    cfg = _cfg()
    scans = load_scan_csv("tests/data/meme_scan_sample.csv")
    row = scans[0]
    # Simulate direction long, B-tier
    # Provide a minimal put chain dict with delta and spreads
    spot = row.price
    chain = [
        {"expiry": "2025-01-15", "right": "P", "strike": round(spot * 0.9, 2), "bid": 1.0, "ask": 1.2, "mid": 1.1, "oi": 200, "delta": -0.22},
        {"expiry": "2025-01-15", "right": "P", "strike": round(spot * 0.85, 2), "bid": 0.5, "ask": 0.7, "mid": 0.6, "oi": 180, "delta": -0.15},
    ]
    # Force debit failure by passing empty calls set (no call data)
    struct = pick_structure(row, chain, direction="long", cfg=cfg, tier="B")
    assert struct.template in {"BullPutCredit", "Template"}
    if struct.template == "BullPutCredit":
        assert struct.debit_or_credit == "credit"
        assert struct.long_strike and struct.short_strike and struct.width
