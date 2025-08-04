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

def test_natural_language_expiry_parsing(monkeypatch):
    import datetime as dt
    import portfolio_exporter.scripts.quick_chain as qc

    # simulate parsing of natural-language expiry
    fake_date = dt.datetime(2100, 12, 31)
    monkeypatch.setattr(qc.dateparser, "parse", lambda raw, settings: fake_date)

    # capture expiry passed to fetch_chain and provide minimal DataFrame
    captured = {}
    fake_df = pd.DataFrame({
        "strike": [], "right": [], "mid": [],
        "bid": [], "ask": [], "delta": [],
        "theta": [], "iv": [],
    })
    def fake_fetch(sym, exp, strikes):
        captured["expiry"] = exp
        return fake_df
    monkeypatch.setattr(
        "portfolio_exporter.core.chain.fetch_chain",
        fake_fetch,
    )

    # inputs: symbol prompt, expiry prompt, then quit
    seq = iter(["TEST", "+30d", "q"])
    monkeypatch.setattr("builtins.input", lambda _="": next(seq))

    qc.run(None, None)
    assert captured.get("expiry") == "2100-12-31"
