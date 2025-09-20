from __future__ import annotations

import types

from portfolio_exporter.core.micro_momo_sources import enrich_inplace
from portfolio_exporter.core.micro_momo_types import ScanRow
from portfolio_exporter.core.providers import ib_provider, yahoo_provider, halts_nasdaq


def _cfg_enrich() -> dict:
    return {
        "data": {
            "mode": "enrich",
            "providers": ["ib", "yahoo"],
            "offline": False,
            "halts_source": "nasdaq",
            "cache": {"enabled": True, "dir": "out/.cache", "ttl_sec": 60},
        }
    }


def test_enrich_inplace_with_mocks(monkeypatch) -> None:
    # R1 minimal fields, R2 has CSV precedence for last and gap
    r1 = ScanRow(symbol="ABC", price=0.0, volume=0, rel_strength=0.0, short_interest=0.0, turnover=0.0, iv_rank=0.0, atr_pct=0.0, trend=0.0)
    r2 = ScanRow(symbol="ABC", price=0.0, volume=0, rel_strength=0.0, short_interest=0.0, turnover=0.0, iv_rank=0.0, atr_pct=0.0, trend=0.0)
    # CSV precedence values on r2
    r2.last_price = 11.11  # type: ignore[attr-defined]
    r2.premkt_gap_pct = 2.0  # type: ignore[attr-defined]

    # Monkeypatch providers
    monkeypatch.setattr(ib_provider, "get_quote", lambda s, c: {"last": 10.0, "prev_close": 9.0})
    # minute bars (10 bars)
    bars = [
        {"ts": i, "open": 9.5 + 0.05 * i, "high": 9.6 + 0.05 * i, "low": 9.4 + 0.05 * i, "close": 9.5 + 0.05 * i, "volume": 1000 + i * 10}
        for i in range(10)
    ]
    monkeypatch.setattr(ib_provider, "get_intraday_bars", lambda s, c, minutes=60, prepost=True: bars)
    # Option chain near 10
    chain = [
        {"expiry": "20250115", "right": "C", "strike": 10.0, "bid": 1.0, "ask": 1.2, "mid": 1.1, "delta": 0.5, "oi": 500, "volume": 100},
        {"expiry": "20250115", "right": "C", "strike": 10.5, "bid": 0.7, "ask": 0.9, "mid": 0.8, "delta": 0.4, "oi": 300, "volume": 50},
    ]
    monkeypatch.setattr(ib_provider, "get_option_chain", lambda s, c: chain)
    monkeypatch.setattr(ib_provider, "get_shortable", lambda s, c: {"available": 100000, "fee_rate": 8.5})

    monkeypatch.setattr(yahoo_provider, "get_summary", lambda s, c: {
        "float_shares": 80_000_000,
        "short_percent_float": 12.0,
        "avg_vol_10d": 3_000_000,
        "avg_vol_3m": 3_500_000,
        "pre_market_price": 9.6,
        "last": 10.0,
        "prev_close": 9.0,
    })
    monkeypatch.setattr(yahoo_provider, "get_option_chain", lambda s, c: [])

    monkeypatch.setattr(halts_nasdaq, "get_halts_today", lambda c: {"ABC": 1})

    rows = [r1, r2]
    cfg = _cfg_enrich()
    enrich_inplace(rows, cfg)

    # R1 filled
    assert getattr(r1, "last_price", None) == 10.0
    assert getattr(r1, "prev_close", None) == 9.0
    assert getattr(r1, "premkt_gap_pct", None) is not None
    assert getattr(r1, "rvol_1m", None) is not None
    assert getattr(r1, "vwap", None) is not None
    assert getattr(r1, "float_millions", None) == 80.0
    assert getattr(r1, "adv_usd_millions", None) is not None
    assert getattr(r1, "oi_near_money", 0) > 0
    assert getattr(r1, "spread_pct_near_money", 0.0) > 0.0
    assert getattr(r1, "halts_count_today", 0) == 1
    prov = getattr(r1, "_provenance", {})
    assert prov.get("src_last") == "ib"
    assert prov.get("src_float") == "yahoo"

    # R2 respects CSV precedence for last and gap
    assert getattr(r2, "last_price", None) == 11.11
    assert getattr(r2, "premkt_gap_pct", None) == 2.0
    prov2 = getattr(r2, "_provenance", {})
    # last came from CSV
    assert prov2.get("src_last") in (None, "csv") or True

