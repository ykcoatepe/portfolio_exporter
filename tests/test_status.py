import builtins, types
from portfolio_exporter.core import ui


class Dummy:
    def __init__(self):
        self.calls = []

    def update(self, text, style="green"):
        self.calls.append((text, style))

    def stop(self):
        pass


def test_status_bar_called(monkeypatch):
    dummy = Dummy()
    monkeypatch.setattr(ui, "StatusBar", lambda *a, **k: dummy)
    import importlib, main as m

    importlib.reload(m)  # re-run main with patch
    m.parse_args = lambda: types.SimpleNamespace(quiet=False, format="csv")
    monkeypatch.setattr(builtins, "input", lambda _: "0")
    m.main()
    assert dummy.calls, "StatusBar.update was never called"
