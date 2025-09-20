import types

import portfolio_exporter.psd_adapter as psd


def test_does_not_cache_miss(monkeypatch):
    calls = {"n": 0}

    def fail_import(name):
        calls["n"] += 1
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(psd.importlib, "import_module", fail_import)
    psd._ENGINE_STATE_CACHE = psd._UNSET

    assert psd._get_positions_engine_state() is None
    assert calls["n"] == 1

    dummy_state = object()
    module = types.SimpleNamespace(_state=dummy_state)

    def ok_import(name):
        calls["n"] += 1
        return module

    monkeypatch.setattr(psd.importlib, "import_module", ok_import)
    assert psd._get_positions_engine_state() is dummy_state
    assert calls["n"] == 2

    assert psd._get_positions_engine_state() is dummy_state
    assert calls["n"] == 2

    psd._ENGINE_STATE_CACHE = psd._UNSET
