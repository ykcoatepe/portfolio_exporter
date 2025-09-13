from portfolio_exporter.core import risk_dash


def test_dashboard_calls_watch(monkeypatch):
    calls = []

    def fake_watch(return_dict=False):
        calls.append(return_dict)
        return {"net_liq": 1.0}

    monkeypatch.setattr("portfolio_exporter.scripts.risk_watch.run", fake_watch)

    class DummyLive:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def update(self, _):
            pass

    monkeypatch.setattr(risk_dash, "Live", DummyLive)
    monkeypatch.setattr(risk_dash.time, "sleep", lambda *_: None)

    risk_dash.run(refresh=0, iterations=1)
    assert calls and calls[0] is True
