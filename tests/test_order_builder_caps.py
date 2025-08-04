import builtins
import types

from portfolio_exporter.scripts import order_builder
from portfolio_exporter.core.config import settings


def test_order_builder_caps(monkeypatch, tmp_path):
    cfg = types.SimpleNamespace(
        slippage=0.05, delta_cap=0, theta_cap=0, confirm_above_caps=True
    )
    object.__setattr__(settings, "order_builder", cfg)
    monkeypatch.setattr(settings, "output_dir", str(tmp_path))

    def fake_quote_option(*args, **kwargs):
        return {
            "mid": 1.0,
            "bid": 0.9,
            "ask": 1.1,
            "delta": 0.0,
            "gamma": 0.0,
            "theta": -1.0,
            "vega": 0.0,
            "iv": 0.2,
        }

    def fake_quote_stock(*args, **kwargs):
        return {"mid": 100.0, "bid": 99.0, "ask": 101.0}

    monkeypatch.setattr(order_builder, "quote_option", fake_quote_option)
    monkeypatch.setattr(order_builder, "quote_stock", fake_quote_stock)

    inputs = iter(["AAPL 150c 2099-01-01 x2", "N"])
    monkeypatch.setattr(builtins, "input", lambda _="": next(inputs))
    prompts = iter(["", ""])
    monkeypatch.setattr(
        builtins, "prompt_toolkit.prompt", lambda *a, **k: next(prompts)
    )

    assert order_builder.run() is False
    tickets = list((tmp_path / "tickets").glob("ticket_*.json"))
    assert not tickets
