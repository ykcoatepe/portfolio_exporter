"""Ensure local virtualenv packages are discoverable when using system Python.

This makes commands like ``python3 -m uvicorn`` work without manually activating
``.venv`` by adding the environment's site-packages (and bin/Scripts directory)
onto ``sys.path`` and ``PATH`` if the virtualenv exists.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable


def _iter_site_packages(venv_root: Path) -> Iterable[Path]:
    """Yield site-packages directories inside *venv_root* if they exist."""

    unix_lib = venv_root / "lib"
    if unix_lib.is_dir():
        yield from (path for path in unix_lib.glob("python*/site-packages") if path.is_dir())

    direct_site_packages = venv_root / "site-packages"
    if direct_site_packages.is_dir():
        yield direct_site_packages

    windows_lib = venv_root / "Lib" / "site-packages"
    if windows_lib.is_dir():
        yield windows_lib


def _ensure_path_entry(path: Path) -> None:
    path_str = str(path)
    if path_str and path.is_dir() and path_str not in sys.path:
        sys.path.insert(0, path_str)


def _maybe_prepend_to_env_path(path: Path) -> None:
    if not path.is_dir():
        return
    current = os.environ.get("PATH", "")
    entries = current.split(os.pathsep) if current else []
    path_str = str(path)
    if path_str in entries:
        return
    os.environ["PATH"] = os.pathsep.join([path_str, current]) if current else path_str


def _bootstrap_virtualenv() -> None:
    repo_root = Path(__file__).resolve().parent
    venv_dir = repo_root / ".venv"
    if not venv_dir.is_dir():
        return

    for site_path in _iter_site_packages(venv_dir):
        _ensure_path_entry(site_path)

    # Ensure console scripts resolve when subprocesses rely on PATH.
    for candidate in (venv_dir / "bin", venv_dir / "Scripts"):
        _maybe_prepend_to_env_path(candidate)


_bootstrap_virtualenv()
