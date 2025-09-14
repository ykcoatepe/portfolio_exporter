from __future__ import annotations

from src.psd.analytics.combos import recognize
from src.psd.models import Position, OptionLeg


def _opt(symbol: str, expiry: str, right: str, strike: float, qty: int, price: float) -> Position:
    return Position(uid=f"{symbol}-{expiry}-{right}-{strike}", symbol=symbol, sleeve="theta", kind="option", qty=qty, mark=price, legs=[OptionLeg(symbol=symbol, expiry=expiry, right=right, strike=strike, qty=qty, price=price, delta=None)])


def test_recognize_iron_condor():
    # Short 100C/100P inside, long 105C/95P outside → IC credit
    legs = [
        _opt("SPY","20260117","C",100, -1, 1.00),
        _opt("SPY","20260117","C",105,  1, 0.20),
        _opt("SPY","20260117","P",100, -1, 1.00),
        _opt("SPY","20260117","P", 95,  1, 0.20),
    ]
    combos, orphans = recognize(legs)
    assert not orphans
    assert combos and combos[0].kind == "iron_condor"
    d = combos[0].to_dict()
    assert round(d["credit"],2) == 1.60
    assert round(d["width_call"],2) == 5.0 and round(d["width_put"],2) == 5.0
    assert round(d["max_loss"],2) == round((5-0.8)*100,2)


def test_recognize_verticals_and_orphan():
    # Bear call only
    legs = [
        _opt("SPY","20260117","C",100, -1, 1.00),
        _opt("SPY","20260117","C",105,  1, 0.40),
        # orphan short put without long hedge
        _opt("SPY","20260117","P",100, -1, 1.00),
    ]
    combos, orphans = recognize(legs)
    assert any(o["reason"] == "orphan-risk" for o in orphans)
    assert combos and combos[0].kind == "credit_spread"

