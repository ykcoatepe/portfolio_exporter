from __future__ import annotations

from src.psd.analytics.exposure import delta_beta_exposure
from src.psd.analytics.var import var95_1d_from_closes
from src.psd.models import OptionLeg, Position


def test_delta_beta_exposure_mixed():
    positions = [
        Position(uid="EQ1", symbol="SPY", sleeve="core", kind="equity", qty=100, mark=400.0, beta=1.0),
        Position(
            uid="OPT1",
            symbol="SPY",
            sleeve="theta",
            kind="option",
            qty=1,
            mark=2.0,
            legs=[OptionLeg(symbol="SPY", expiry="20250117", right="C", strike=420.0, qty=1, price=2.0, delta=0.25)],
        ),
    ]
    nav = 100_000.0
    d_beta = delta_beta_exposure(positions, nav)
    # equity: 100*400 / 100k = 0.4; option: 0.25*100*2*1 / 100k = 0.0005
    assert round(d_beta, 4) == 0.4005


def test_var95_historical_and_parametric():
    closes = [100, 101, 100, 99, 100, 98, 97, 99, 100, 101, 102, 100]
    nav_exposed = 50_000.0
    v = var95_1d_from_closes(closes, nav_exposed)
    assert v > 0
    v2 = var95_1d_from_closes([100, 101], nav_exposed)
    assert v2 > 0

