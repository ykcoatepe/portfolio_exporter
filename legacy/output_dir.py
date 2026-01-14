from __future__ import annotations

import os
from pathlib import Path


DEFAULT_OUTPUT_DIR = (
    "/Users/yordamkocatepe/Library/Mobile Documents/"
    "com~apple~CloudDocs/Downloads"
)


def resolve_output_dir() -> Path:
    """Return a writable output directory for legacy scripts.

    Prefers OUTPUT_DIR/PE_OUTPUT_DIR when set, otherwise the historical
    default path. Falls back to a repo-local tmp directory if the target
    is not writable (e.g., in CI).
    """

    base = os.getenv("OUTPUT_DIR") or os.getenv("PE_OUTPUT_DIR") or DEFAULT_OUTPUT_DIR
    candidate = Path(base).expanduser()
    try:
        candidate.mkdir(parents=True, exist_ok=True)
        test_file = candidate / ".pe_write_test"
        with test_file.open("wb") as handle:
            handle.write(b"ok")
        try:
            test_file.unlink()
        except Exception:
            pass
        return candidate
    except Exception:
        fallback = Path("./tmp_test_run")
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback
