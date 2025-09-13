"""
Smoke-test the interactive CLI by simulating keystrokes for every
currently-implemented menu item.  Heavy scripts are monkey-patched
to lightweight stubs so the test runs in <1 s.
"""

import builtins
import importlib
import types
import main
from portfolio_exporter import scripts


# 1-A  Patch ALL .run functions to fast stubs
def _stub_runs(monkeypatch: types.SimpleNamespace) -> None:
    for name in dir(scripts):
        mod = getattr(scripts, name)
        if isinstance(mod, types.ModuleType) and hasattr(mod, "run"):
            monkeypatch.setattr(mod, "run", lambda *a, **k: None)
    from portfolio_exporter.core import risk_dash, caps_dash

    monkeypatch.setattr(risk_dash, "run", lambda *a, **k: None)
    monkeypatch.setattr(caps_dash, "run", lambda *a, **k: None)


# 1-B  Input sequence that walks every key:
# 1-B  Input sequence that walks every key:
# Main: 1 Pre-Market  →  s h p o n z r
#       2 Live-Market →  q t g r c b
#       3 Trades      →  e b l q v r
#       4 Portfolio Greeks → r
# Exit
keys = [
    "1",
    "s",
    "h",
    "p",
    "o",
    "n",
    "z",
    "r",
    "2",
    "q",
    "t",
    "g",
    "r",
    "c",
    "u",
    "b",
    "3",
    "e",
    "b",
    "l",
    "q",
    "v",
    "r",
    "4",
    "r",
    "0",
]
seq = iter(keys)


def fake_input(_=""):
    return next(seq)


def test_full_menu(monkeypatch):
    _stub_runs(monkeypatch)
    # force quiet mode for clean output
    monkeypatch.setattr(builtins, "input", fake_input)
    main.parse_args = lambda: types.SimpleNamespace(quiet=True, format="csv")
    importlib.reload(main)
    # should exit 0 without exceptions
    main.main()
