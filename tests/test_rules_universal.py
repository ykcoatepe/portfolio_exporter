from __future__ import annotations

from src.psd.rules.universal import compute_1r, oco_levels, credit_spread_tp_sl


def test_equity_oco_levels():
    one_r = compute_1r(qty=10, entry=100.0)
    stop, target = oco_levels(entry=100.0, one_r=one_r, stop_R=-1.0, target_R=2.0)
    assert round(stop, 2) == 0.0  # 100 * (1-1.0)
    assert round(target, 2) == 300.0  # 100 * (1+2.0)


def test_credit_spread_tp_sl():
    out = credit_spread_tp_sl(credit=1.00, width=5.00, tp_capture=0.50)
    assert out["max_loss"] == 4.0
    assert out["tp_debit"] == 0.5
    assert out["sl_debit"] == 5.0

