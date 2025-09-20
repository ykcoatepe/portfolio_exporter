"""Lightweight import shim to access in-repo `src.psd` package as `psd`.

This keeps imports like `from psd.runner import start_psd` working without
installing a separate distribution for PSD.
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from types import ModuleType

_pkg_dir = Path(__file__).resolve().parent
_src_pkg = _pkg_dir.parent / "src" / "psd"
if _src_pkg.exists():  # include src/psd modules when running from repo root
    __path__.append(str(_src_pkg))  # type: ignore[name-defined]

__all__: list[str] = []


def __getattr__(name: str) -> ModuleType:
    try:
        return import_module(f"{__name__}.{name}")
    except ModuleNotFoundError as exc:  # pragma: no cover - passthrough attr errors
        raise AttributeError(name) from exc
