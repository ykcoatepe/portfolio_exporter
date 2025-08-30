import contextlib, io, importlib
import pytest

from portfolio_exporter.core import caps_dash


def test_caps_dash(monkeypatch):
    monkeypatch.setattr(
        "portfolio_exporter.scripts.theta_cap.run",
        lambda return_dict=False: {"theta_pct": 0.35, "net_delta": -0.72},
    )
    monkeypatch.setattr(
        "portfolio_exporter.scripts.gamma_scalp.run",
        lambda return_dict=False: {"used_bucket": 0.12},
    )
    # Skip sleep
    monkeypatch.setattr(
        caps_dash, "sleep", lambda x: (_ for _ in ()).throw(KeyboardInterrupt)
    )
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        caps_dash.run()
    out = buf.getvalue()
    assert "Theta / Gamma Caps" in out
    assert "+35.0%" in out
    assert "-0.72" in out
    assert "12.0%" in out
