from __future__ import annotations

import datetime
import shutil
import subprocess
import webbrowser
from pathlib import Path

CURATED = [
    "micro_momo_dashboard.html",
    "micro_momo_orders.csv",
    "micro_momo_basket.csv",
    "micro_momo_basket_ib_notes.txt",
    "micro_momo_scored.csv",
    "micro_momo_journal.csv",
    "micro_momo_eod_summary.csv",
    "micro_momo_triggers_log.csv",
]


def publish_pack(src_out: str = "out", dst_root: str | None = None) -> str:
    """Curate a daily pack under publish/YYYY-MM-DD from `src_out`.

    Copies a minimal set of Micro-MOMO artifacts if present.

    Returns the destination directory as a string.
    """
    src = Path(src_out).expanduser()
    dst_root_path = Path(dst_root) if dst_root else (src / "publish")
    day = datetime.date.today().strftime("%Y-%m-%d")
    dst = dst_root_path / day
    dst.mkdir(parents=True, exist_ok=True)
    for name in CURATED:
        p = src / name
        if p.exists():
            shutil.copy2(p, dst / name)
    return str(dst)


def open_in_finder(path: str) -> None:
    """Open a file or directory via macOS `open` (no-op on failure)."""
    try:
        subprocess.run(["open", path], check=False)
    except Exception:
        pass


def open_dashboard(path_dir: str) -> None:
    """Open the curated dashboard HTML if present (mac-friendly).

    Prefers macOS `open` and falls back to the default web browser.
    """
    dash = Path(path_dir) / "micro_momo_dashboard.html"
    if dash.exists():
        try:
            subprocess.run(["open", str(dash)], check=False)
        except Exception:
            webbrowser.open(dash.absolute().as_uri(), new=2)
