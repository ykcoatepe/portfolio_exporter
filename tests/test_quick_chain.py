import pandas as pd
from portfolio_exporter.scripts import quick_chain


def test_chain_mark_for_builder(monkeypatch):
    fake_df = pd.DataFrame(
        {
            "strike": [100, 105],
            "right": ["C", "P"],
            "mid": [1.2, 1.3],
            "bid": [1.1, 1.25],
            "ask": [1.3, 1.35],
            "delta": [0.5, -0.5],
            "theta": [-0.02, -0.01],
            "iv": [0.23, 0.24],
        }
    )
    monkeypatch.setattr(
        "portfolio_exporter.core.chain.fetch_chain",
        lambda *a, **kw: fake_df,
    )
    seq = iter(["", "", " ", "\x1b[B", " ", "b", "q"])
    monkeypatch.setattr("builtins.input", lambda _="": next(seq))
    called = {}
    monkeypatch.setattr(
        "portfolio_exporter.scripts.order_builder.run",
        lambda *a, **k: called.setdefault("yes", True),
    )
    quick_chain.run("FAKE", "2099-01-01")
    assert called.get("yes")
