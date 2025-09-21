# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

# Placeholder for IBKR PDF ingestion until the parser lands.

_IB_PDF_PATH = Path("/mnt/data/X_all.pdf")


def detect_ib_pdf(path: Path | None = None) -> dict[str, str]:
    """Detect whether the expected IBKR PDF exists yet.

    The full parser will be implemented in a later milestone. Returning an empty
    payload keeps the interface wired for now.
    """

    target = path or _IB_PDF_PATH
    if target.exists():
        return {"path": str(target)}
    return {}
