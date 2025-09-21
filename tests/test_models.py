from __future__ import annotations

import pytest

from src.psd.models import OptionLeg, Position, RiskSnapshot


def test_option_leg_validation():
    leg = OptionLeg(symbol="AAPL", expiry="20250117", right="C", strike=150.0, qty=1, price=2.5, delta=0.4)
    assert leg.symbol == "AAPL"
    with pytest.raises(ValueError):
        OptionLeg(symbol="", expiry="20250117", right="C", strike=150.0, qty=1, price=2.5)
    with pytest.raises(ValueError):
        OptionLeg(symbol="AAPL", expiry="20250117", right="C", strike=0.0, qty=1, price=2.5)
    with pytest.raises(ValueError):
        OptionLeg(symbol="AAPL", expiry="20250117", right="C", strike=150.0, qty=0, price=2.5)


def test_position_validation():
    p = Position(uid="EQ-1", symbol="MSFT", sleeve="core", kind="equity", qty=10, mark=320.0, beta=1.1)
    assert p.uid == "EQ-1"
    with pytest.raises(ValueError):
        Position(uid="", symbol="MSFT", sleeve="core", kind="equity", qty=10, mark=320.0)
    with pytest.raises(ValueError):
        Position(uid="X", symbol="", sleeve="core", kind="equity", qty=10, mark=320.0)
    with pytest.raises(ValueError):
        Position(uid="X", symbol="MSFT", sleeve="core", kind="credit_spread", qty=1, mark=1.0, legs=[])


def test_risk_snapshot_validation():
    s = RiskSnapshot(nav=100000.0, vix=18.0)
    assert s.nav == 100000.0
    with pytest.raises(ValueError):
        RiskSnapshot(nav=0.0, vix=18.0)
    with pytest.raises(ValueError):
        RiskSnapshot(nav=100000.0, vix=-1.0)

