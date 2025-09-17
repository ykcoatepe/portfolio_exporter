from __future__ import annotations

"""Bridge between the legacy Portfolio Exporter main menu and PSD ops menu."""

from typing import Any


def launch(status: Any, fmt: str) -> None:  # noqa: ARG001 - fmt reserved for future
    """Delegate to the standalone PSD ops menu used by ``python -m psd.menus.ops``."""

    if status:
        try:
            status.update("Launching PSD Ops menu", "cyan")
        except Exception:  # pragma: no cover - defensive: status may not support update
            pass

    from psd.menus import ops as psd_ops  # type: ignore

    try:
        psd_ops.main()
    finally:
        if status:
            try:
                status.update("Ready", "green")
            except Exception:  # pragma: no cover
                pass
