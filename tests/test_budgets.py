from __future__ import annotations

from src.psd.rules.budgets import theta_weekly_fees, hedge_monthly_carry


def test_budget_warns():
    # theta weekly > 0.10%
    th = theta_weekly_fees(nav=100_000.0, fees_week_to_date=150.0, threshold=0.001)
    assert th["warn"] is True
    # hedge monthly > 0.35%
    hd = hedge_monthly_carry(nav=100_000.0, hedge_cost_mtd=360.0, cap=0.0035)
    assert hd["warn"] is True

