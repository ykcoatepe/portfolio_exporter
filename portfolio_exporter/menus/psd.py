from __future__ import annotations

"""TUI menu wrapper for the Portfolio Sentinel Dashboard (PSD).

Provides a minimal screen that renders the PSD dashboard using the same
callable as the CLI helper and offers a simple Back/Refresh UX.
"""

from typing import Any

from rich.console import Console
from rich.panel import Panel

try:
    # StatusBar is optional in tests; keep signature consistent with other menus
    from portfolio_exporter.core.ui import StatusBar  # noqa: F401
except Exception:  # pragma: no cover - import safety in minimal envs
    StatusBar = object  # type: ignore

_AUTO_STARTED = False


def launch(status: Any, fmt: str) -> None:  # noqa: ARG001 - fmt reserved for future
    """Render the PSD dashboard and provide a simple Back/Refresh loop."""
    console: Console = status.console if status and hasattr(status, "console") else Console()

    # One-time auto-starter per session
    global _AUTO_STARTED
    try:
        if not _AUTO_STARTED:
            # Load psd.auto defaults via runner helper to avoid YAML parsing here
            from psd.runner import load_auto_defaults  # type: ignore  # noqa: I001

            auto_cfg = load_auto_defaults()
            if bool(auto_cfg.get("start_on_menu", True)):
                _AUTO_STARTED = True

                def _run() -> None:
                    try:
                        from psd.runner import start_psd  # type: ignore  # noqa: I001

                        host, port = start_psd(loops=None, interval_override=None)
                        print(f"[psd] started at http://{host}:{port} and opened browser")
                    except Exception as e:  # pragma: no cover - best-effort logging
                        print(f"[psd] auto-start failed: {e}")

                import threading  # noqa: I001

                threading.Thread(target=_run, name="psd-auto-start", daemon=True).start()
    except Exception:
        # Ignore auto-start errors; menu remains functional
        pass

    def _render_once() -> None:
        if status:
            status.update("Rendering Portfolio Sentinel", "cyan")
        try:
            # Use the shared callable also used by `pe psd dash`
            from src.psd.ui.cli import run_dash  # type: ignore

            run_dash()
        finally:
            if status:
                status.update("Ready", "green")

    while True:
        console.rule("[bold]Portfolio Sentinel")
        _render_once()
        console.print(Panel.fit("[dim]Actions:[/] r=Refresh   o=Open in browser   b/q=Back"), highlight=False)
        try:
            # Reuse StatusBar-aware prompt if available
            from portfolio_exporter.core import ui as core_ui

            raw = core_ui.prompt_input("› ").strip().lower()
        except Exception:  # pragma: no cover - fallback
            raw = input("› ").strip().lower()
        if raw in {"b", "q", "0"}:
            return
        if raw in {"r", ""}:  # empty input quickly re-renders
            # Loop will re-render
            continue
        if raw in {"o"}:
            try:
                # Run the same starter in background
                from psd.runner import start_psd  # type: ignore  # noqa: I001
                import threading  # noqa: I001

                threading.Thread(target=start_psd, name="psd-starter", daemon=True).start()
                console.print("Opened PSD in your browser (starter is running).", style="green")
            except Exception:
                console.print("Failed to start browser dashboard.", style="red")
            continue
        # Unknown input → ignore and re-render
