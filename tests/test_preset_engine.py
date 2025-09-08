import pandas as pd

from portfolio_exporter.core.preset_engine import (
    suggest_credit_vertical,
    suggest_debit_vertical,
    suggest_iron_condor,
    LiquidityRules,
)


def _make_chain(spot=100.0):
    strikes = [90, 95, 100, 105, 110]
    # simple synthetic quotes: wider ITM, narrower OTM, tight spreads
    calls = []
    puts = []
    for k in strikes:
        # Calls: ITM (k<spot) higher price; OTM lower
        call_mid = max(0.5, (spot - k) * 0.6 + 2)
        put_mid = max(0.5, (k - spot) * 0.6 + 2)
        c_spread = max(0.02, 0.02 * call_mid)
        p_spread = max(0.02, 0.02 * put_mid)
        calls.append({
            "strike": float(k),
            "bid": call_mid - c_spread / 2,
            "ask": call_mid + c_spread / 2,
            "impliedVolatility": 0.25,
            "openInterest": 1000,
            "volume": 500,
        })
        puts.append({
            "strike": float(k),
            "bid": put_mid - p_spread / 2,
            "ask": put_mid + p_spread / 2,
            "impliedVolatility": 0.25,
            "openInterest": 1000,
            "volume": 500,
        })
    return pd.DataFrame(calls), pd.DataFrame(puts)


def test_credit_vertical_bear_call_offline():
    calls, puts = _make_chain()
    rules = LiquidityRules(min_oi=10, min_volume=10, max_spread_pct=0.2)
    cands = suggest_credit_vertical(
        symbol="TEST",
        expiry="2025-10-17",
        side="bear_call",
        profile="balanced",
        rules=rules,
        df_calls=calls,
        df_puts=puts,
        spot_override=100.0,
        avoid_earnings=False,
    )
    assert isinstance(cands, list)
    assert len(cands) >= 1
    c = cands[0]
    assert len(c["legs"]) == 2
    assert all(leg["right"] == "C" for leg in c["legs"])  # call spread


def test_debit_vertical_bull_call_offline():
    calls, puts = _make_chain()
    rules = LiquidityRules(min_oi=10, min_volume=10, max_spread_pct=0.2)
    cands = suggest_debit_vertical(
        symbol="TEST",
        expiry="2025-10-17",
        side="bull_call",
        profile="balanced",
        rules=rules,
        df_calls=calls,
        df_puts=puts,
        spot_override=100.0,
        avoid_earnings=False,
    )
    assert len(cands) >= 1
    c = cands[0]
    assert len(c["legs"]) == 2
    assert all(leg["right"] == "C" for leg in c["legs"])  # call vertical
    assert 0.0 < c.get("debit_frac", 0.0) < 1.0


def test_iron_condor_offline():
    calls, puts = _make_chain()
    rules = LiquidityRules(min_oi=10, min_volume=10, max_spread_pct=0.2)
    cands = suggest_iron_condor(
        symbol="TEST",
        expiry="2025-11-21",
        profile="balanced",
        rules=rules,
        df_calls=calls,
        df_puts=puts,
        spot_override=100.0,
        avoid_earnings=False,
    )
    assert len(cands) >= 1
    c = cands[0]
    assert len(c["legs"]) == 4
    rights = [leg["right"] for leg in c["legs"]]
    assert rights.count("C") == 2 and rights.count("P") == 2
