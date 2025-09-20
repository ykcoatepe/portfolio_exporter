from datetime import time

from portfolio_exporter.core.market_calendar import infer_close_et


def test_override_env_forces_early_close(monkeypatch):
    monkeypatch.setenv("MOMO_SEN_EARLY_CLOSE_TODAY", "1")
    t = infer_close_et()
    assert t == time(13, 0)

