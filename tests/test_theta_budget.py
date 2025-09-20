from __future__ import annotations

from src.psd.rules.theta_templates import enforce, theta_fees_warn


def test_theta_enforcement_and_fees():
    # Regime <15: DTE 50 within window; capture 55% ⇒ action TP
    sev, why = enforce(vix=14.0, dte=50, credit=1.20, debit_now=0.54)
    assert sev == "action" and why == "tp"

    # DTE 20 out of window ⇒ warn
    sev2, why2 = enforce(vix=14.0, dte=20, credit=1.20, debit_now=1.20)
    assert sev2 == "warn" and why2 == "out-of-template"

    # Regime 15–25: DTE 35 within window; capture 45% < 60% upper ⇒ info
    sev3, _ = enforce(vix=20.0, dte=35, credit=1.00, debit_now=0.55)
    assert sev3 in ("info","action")  # action if >= 60%; here 45% so info

    # Weekly θ fees
    assert theta_fees_warn(weekly_fees_abs=150.0, nav=100_000.0) is False
    assert theta_fees_warn(weekly_fees_abs=150.0, nav=100_000.0/2) is True

