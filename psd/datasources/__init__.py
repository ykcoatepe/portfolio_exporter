from __future__ import annotations

from importlib import import_module
from pathlib import Path

__all__: list[str] = []

_pkg_dir = Path(__file__).resolve().parent
_src_pkg = _pkg_dir.parent.parent / "src" / "psd" / "datasources"
if _src_pkg.exists():
    __path__.append(str(_src_pkg))  # type: ignore[name-defined]

try:  # pragma: no cover - mirrors src package at runtime
    _impl = import_module("src.psd.datasources")
except ModuleNotFoundError:  # pragma: no cover - fallback when src missing
    _impl = None
else:
    for _name in ("resolve_msb_source", "is_offline"):
        if hasattr(_impl, _name):
            globals()[_name] = getattr(_impl, _name)
            __all__.append(_name)
