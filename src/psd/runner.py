"""Internal starter for the Portfolio Sentinel Dashboard (PSD).

This module provides a Typer‑free, importable starter used by the TUI menu and
optional dev/ops helpers. It keeps imports light and avoids side effects at
module import time for fast startup.
"""

from __future__ import annotations

from typing import Any, Tuple


def load_auto_defaults() -> dict[str, Any]:
    """Load psd.auto defaults from ``config/rules.yaml`` with safe fallbacks.

    Returns a shallow dict with keys:
    - open_browser: bool
    - web_host: str
    - web_port: int (0 selects a free port)
    - interval_sec: float
    - start_on_menu: bool (whether to auto-start from TUI menu)
    - ib: { connect_retries, backoff_sec[], require_initial_positions, initial_timeout_sec }
    """
    defaults: dict[str, Any] = {
        "open_browser": True,
        "web_host": "127.0.0.1",
        "web_port": 0,
        "interval_sec": 60,
        "start_on_menu": True,
        "ib": {
            "connect_retries": 10,
            "backoff_sec": [1, 2, 3, 5],
            "require_initial_positions": True,
            "initial_timeout_sec": 20,
        },
    }
    try:
        import os

        path = os.path.join("config", "rules.yaml")
        if not os.path.exists(path):
            return defaults
        try:
            import yaml  # type: ignore

            with open(path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
        except Exception:
            return defaults
        auto = (((data or {}).get("psd") or {}).get("auto")) or {}
        if isinstance(auto, dict):
            merged = dict(defaults)
            ib = dict(defaults["ib"])  # type: ignore[index]
            ib.update(auto.get("ib", {}) or {})
            merged.update({k: v for k, v in auto.items() if k != "ib"})
            merged["ib"] = ib
            # Ensure presence of start_on_menu with a safe default
            if "start_on_menu" not in merged:
                merged["start_on_menu"] = True
            return merged
        return defaults
    except Exception:
        return defaults


def start_psd(*, loops: int | None = None, interval_override: float | None = None) -> Tuple[str, int]:
    """One-step PSD starter: web + browser(optional) + IB probe + scheduler.

    - Starts the web server on a free port (when 0) in background.
    - Opens the browser if configured via psd.auto.open_browser.
    - Probes IB positions with retry/backoff (best effort, time-bound).
    - Runs the paced scheduler loop; when ``loops`` is provided, exits after N iterations.

    Returns (host, port) of the web server.
    """
    # Lazy imports to keep import time snappy and avoid hard deps in environments
    # that only exercise the TUI text renderer.
    # Prefer already-imported modules in sys.modules so monkeypatching works
    import sys as _sys
    import importlib as _importlib

    _sys_modules = _sys.modules
    if "psd.web.server" not in _sys_modules and "src.psd.web.server" in _sys_modules:
        _sys_modules["psd.web.server"] = _sys_modules["src.psd.web.server"]
    if "psd.sentinel.sched" not in _sys_modules and "src.psd.sentinel.sched" in _sys_modules:
        _sys_modules["psd.sentinel.sched"] = _sys_modules["src.psd.sentinel.sched"]
    if "psd.datasources.ibkr" not in _sys_modules and "src.psd.datasources.ibkr" in _sys_modules:
        _sys_modules["psd.datasources.ibkr"] = _sys_modules["src.psd.datasources.ibkr"]

    web = _importlib.import_module("psd.web.server" if "psd.web.server" in _sys_modules else "src.psd.web.server")
    sched = _importlib.import_module("psd.sentinel.sched" if "psd.sentinel.sched" in _sys_modules else "src.psd.sentinel.sched")

    # IBKR datasource is optional; tests will monkeypatch as needed
    ib_get_positions = None
    try:
        ds_module = "psd.datasources.ibkr" if "psd.datasources.ibkr" in _sys_modules else "src.psd.datasources.ibkr"
        ib_mod = _importlib.import_module(ds_module)
        ib_get_positions = getattr(ib_mod, "get_positions", None)
    except Exception:
        ib_get_positions = None

    cfg = load_auto_defaults()
    host = str(cfg.get("web_host", "127.0.0.1"))
    port = int(cfg.get("web_port", 0))
    interval = float(interval_override if interval_override is not None else cfg.get("interval_sec", 60))

    # Start web server in background and open browser if requested
    web_started = True
    try:
        host, port = web.start(host=host, port=port, background=True)
    except ModuleNotFoundError:
        web_started = False
    except RuntimeError as exc:
        if "uvicorn" in str(exc).lower() or "fastapi" in str(exc).lower():
            web_started = False
        else:
            raise
    url = f"http://{host}:{int(port)}"
    if web_started and bool(cfg.get("open_browser", True)):
        try:
            import webbrowser

            webbrowser.open(url)
        except Exception:
            pass

    # Probe IB positions with retry/backoff until snapshot available (or timeout)
    ib_cfg = dict(cfg.get("ib", {}))
    retries = int(ib_cfg.get("connect_retries", 10))
    require_pos = bool(ib_cfg.get("require_initial_positions", True))
    backoffs = list(ib_cfg.get("backoff_sec", [1, 2, 3, 5])) or [1]
    timeout = int(ib_cfg.get("initial_timeout_sec", 20))

    import time as _time

    # Ensure an asyncio event loop exists in this thread for ib_insync consumers
    try:
        import asyncio as _asyncio

        _asyncio.get_running_loop()
    except Exception:
        try:
            loop = _asyncio.new_event_loop()
            _asyncio.set_event_loop(loop)
        except Exception:
            pass

    start_ts = _time.monotonic()
    attempt = 0
    while attempt < retries and (_time.monotonic() - start_ts) <= timeout:
        attempt += 1
        positions = []
        try:
            if callable(ib_get_positions):
                positions = ib_get_positions({})  # type: ignore[arg-type]
        except Exception:
            positions = []
        if not require_pos or (positions and len(positions) > 0):
            break
        try:
            print("[psd] waiting for IB positions …")
        except Exception:
            pass
        _time.sleep(float(backoffs[(attempt - 1) % len(backoffs)]))

    # Run scheduler (bounded in tests via loops) and broadcast to web clients
    sched.run_loop(
        interval=int(interval),
        cfg={},
        loops=loops,
        web_broadcast=lambda dto: web.broadcast(dto),
    )
    return host, port
