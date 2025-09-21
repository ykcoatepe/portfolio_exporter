from __future__ import annotations

import time
from typing import Any

import pytest


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


def test_start_psd_dashboard_raises_when_process_exits(monkeypatch: Any, tmp_path: Any) -> None:
    import portfolio_exporter.menus.psd as psd_menu

    dist_path = tmp_path / "dist" / "index.html"
    dist_path.parent.mkdir(parents=True, exist_ok=True)
    dist_path.write_text("", encoding="utf-8")

    class DummyProc:
        def __init__(self) -> None:
            self.returncode = 7

        def poll(self) -> int:
            return self.returncode

    monkeypatch.setattr(psd_menu, "DIST_INDEX", dist_path)
    monkeypatch.setattr(psd_menu, "_ensure_uvicorn_runtime", lambda: None)
    monkeypatch.setattr(psd_menu, "_load_psd_env", lambda: {})
    monkeypatch.setattr(psd_menu, "_port_open", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(psd_menu.subprocess, "Popen", lambda *a, **k: DummyProc())

    with pytest.raises(RuntimeError) as excinfo:
        psd_menu.start_psd_dashboard()

    assert "exit code 7" in str(excinfo.value)


def test_launch_reports_failure(monkeypatch: Any) -> None:
    import portfolio_exporter.menus.psd as psd_menu

    messages: list[tuple[Any, str]] = []

    def fake_notify(status: Any, message: str) -> None:
        messages.append((status, message))

    def fake_start() -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(psd_menu, "_port_open", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(psd_menu, "start_psd_dashboard", fake_start)
    monkeypatch.setattr(psd_menu, "_notify_psd_error", fake_notify)

    psd_menu._AUTO_STARTED = False  # type: ignore[attr-defined]

    psd_menu.launch(status=None, fmt="csv")

    assert psd_menu._AUTO_STARTED is False  # type: ignore[attr-defined]
    assert messages == [(None, "boom")]
