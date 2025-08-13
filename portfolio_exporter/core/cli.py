"""Shared CLI helpers.

Provides small utilities to keep behaviour across scripts
consistent.  Each helper is intentionally tiny and free of any
third‑party dependencies so importing this module has negligible
startup cost.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

from .config import settings


def resolve_output_dir(arg: str | None) -> Path:
    """Return the effective output directory.

    Preference order:
    1. Explicit argument ``arg``.
    2. ``OUTPUT_DIR`` environment variable.
    3. ``PE_OUTPUT_DIR`` environment variable (backwards compatibility).
    4. ``settings.output_dir`` from configuration.
    """

    env = os.getenv("OUTPUT_DIR") or os.getenv("PE_OUTPUT_DIR")
    base = arg or env or settings.output_dir
    return Path(base).expanduser()


def resolve_quiet(no_pretty: bool) -> tuple[bool, bool]:
    """Determine quiet/pretty flags.

    ``PE_QUIET=1`` forces quiet mode regardless of ``no_pretty``.
    Returns ``(quiet, pretty)``.
    """

    quiet_env = os.getenv("PE_QUIET") not in (None, "", "0")
    quiet = bool(quiet_env)
    pretty = not quiet and not no_pretty
    return quiet, pretty


def decide_file_writes(
    args: Any,
    *,
    json_only_default: bool,
    defaults: Dict[str, bool],
) -> Dict[str, bool]:
    """Determine which output formats should be written.

    ``defaults`` maps format names to their default enabled state.
    ``json_only_default`` controls whether ``--json`` without an
    ``--output-dir`` disables file writes.
    """

    formats = {k: bool(getattr(args, k, False)) for k in defaults}
    if getattr(args, "no_files", False):
        return {k: False for k in defaults}

    if any(formats.values()):
        return formats

    if json_only_default and getattr(args, "json", False) and getattr(args, "output_dir", None) is None:
        return {k: False for k in defaults}

    return defaults


def print_json(data: Dict[str, Any], quiet: bool) -> None:
    """Emit JSON to STDOUT.

    Always prints compact JSON (no whitespace).  ``quiet`` is accepted so
    callers can unconditionally pass the value returned from
    :func:`resolve_quiet`; JSON is still printed in quiet mode.
    """

    txt = json.dumps(data, separators=(",", ":"))
    print(txt)
