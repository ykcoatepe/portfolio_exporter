from __future__ import annotations

import time
from typing import Any


def test_menu_auto_start_called_once(monkeypatch: Any) -> None:
    calls = {"start": 0, "open": 0}

    import portfolio_exporter.menus.psd as psd_menu

    def fake_start() -> None:
        calls["start"] += 1

    def fake_open() -> None:
        calls["open"] += 1

    monkeypatch.setattr(psd_menu, "start_psd_dashboard", fake_start)
    monkeypatch.setattr(psd_menu, "_open_dash_tab", fake_open)
    monkeypatch.setattr(psd_menu, "_port_open", lambda *_args, **_kwargs: True)

    psd_menu._AUTO_STARTED = False  # type: ignore[attr-defined]

    psd_menu.launch(status=None, fmt="csv")
    time.sleep(0.01)
    psd_menu.launch(status=None, fmt="csv")
    time.sleep(0.01)

    assert calls == {"start": 1, "open": 1}
