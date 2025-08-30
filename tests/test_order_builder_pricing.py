import builtins
import json
import pathlib
import types

from portfolio_exporter.scripts import order_builder
from portfolio_exporter.core.config import settings


def test_order_builder_pricing(monkeypatch, tmp_path):
    cfg = types.SimpleNamespace(
        slippage=0.05, delta_cap=500, theta_cap=-100, confirm_above_caps=True
    )
    object.__setattr__(settings, "order_builder", cfg)
    monkeypatch.setattr(settings, "output_dir", str(tmp_path))

    def fake_quote_option(*args, **kwargs):
        return {
            "mid": 1.0,
            "bid": 0.9,
            "ask": 1.1,
            "delta": 0.5,
            "gamma": 0.1,
            "theta": -0.02,
            "vega": 0.2,
            "iv": 0.3,
        }

    def fake_quote_stock(*args, **kwargs):
        return {"mid": 100.0, "bid": 99.0, "ask": 101.0}

    monkeypatch.setattr(order_builder, "quote_option", fake_quote_option)
    monkeypatch.setattr(order_builder, "quote_stock", fake_quote_stock)

    inputs = iter(["AAPL 150c 2099-01-01 x2", "y"])
    monkeypatch.setattr(builtins, "input", lambda _="": next(inputs))
    prompts = iter(["", ""])
    monkeypatch.setattr(
        builtins, "prompt_toolkit.prompt", lambda *a, **k: next(prompts)
    )

    assert order_builder.run() is True

    previews = list(tmp_path.glob("order_preview_*.csv"))
    assert previews, "preview CSV not created"

    tickets = list((tmp_path / "tickets").glob("ticket_*.json"))
    assert tickets, "ticket JSON not written"
    data = json.loads(tickets[0].read_text())
    assert isinstance(data.get("mid_prices"), list)
    assert "net_delta" in data and "net_theta" in data
