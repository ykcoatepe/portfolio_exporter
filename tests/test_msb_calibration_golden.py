import numpy as np
import pandas as pd

from psd.analytics.msb import compute_msb


def _build_series(
    hy_level: float,
    vx1_level: float,
    vx2_level: float,
    periods: int = 160,
    trend: float = 0.0,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    idx = pd.bdate_range("2023-01-02", periods=periods)
    steps = pd.Series(np.linspace(0.0, trend, periods), index=idx)
    hy = pd.Series(hy_level, index=idx) + steps
    vx1 = pd.Series(vx1_level, index=idx) + 0.75 * steps
    vx2 = pd.Series(vx2_level, index=idx) + 0.25 * steps
    return hy, vx1, vx2


def test_msb_calm_regime_stays_benign():
    hy, vx1, vx2 = _build_series(4.0, 18.0, 20.0, trend=0.0)
    df = compute_msb(hy=hy, vx1=vx1, vx2=vx2, window=60, fallback=20)
    tail_median = df["msb"].tail(30).median()
    assert 20.0 <= tail_median <= 35.0


def test_msb_stress_regime_crosses_high_threshold():
    hy, vx1, vx2 = _build_series(8.0, 45.0, 30.0, trend=2.0)
    df = compute_msb(hy=hy, vx1=vx1, vx2=vx2, window=60, fallback=20)
    tail_mean = df["msb"].tail(30).mean()
    assert tail_mean >= 80.0
