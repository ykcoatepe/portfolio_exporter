from __future__ import annotations

import sys
import time
from types import ModuleType
from typing import Any


def test_menu_auto_start_called_once(monkeypatch: Any) -> None:
    # Ensure PSD UI render doesn't import heavy modules
    fake_ui = ModuleType("src.psd.ui.cli")

    def _run_dash() -> None:
        return None

    fake_ui.run_dash = _run_dash  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "src.psd.ui.cli", fake_ui)

    # Stub runner defaults to enable auto start
    calls = {"n": 0}

    def fake_defaults() -> dict[str, Any]:
        return {"start_on_menu": True}

    def fake_start_psd(**_kwargs: Any) -> tuple[str, int]:
        calls["n"] += 1
        return ("127.0.0.1", 8123)

    import psd.runner as runner

    monkeypatch.setattr(runner, "load_auto_defaults", fake_defaults)
    monkeypatch.setattr(runner, "start_psd", fake_start_psd)

    # Make user input return immediately to exit the screen after one render
    try:
        import portfolio_exporter.core.ui as core_ui  # type: ignore

        monkeypatch.setattr(core_ui, "prompt_input", lambda _p: "0")
    except Exception:
        monkeypatch.setattr("builtins.input", lambda _p: "0")

    # Reset auto-start sentinel between invocations
    import portfolio_exporter.menus.psd as psd_menu

    psd_menu._AUTO_STARTED = False  # type: ignore[attr-defined]

    # Call launch twice; auto starter should run once
    psd_menu.launch(status=None, fmt="csv")
    # Give background thread a moment
    time.sleep(0.05)
    psd_menu.launch(status=None, fmt="csv")
    time.sleep(0.05)

    assert calls["n"] == 1
