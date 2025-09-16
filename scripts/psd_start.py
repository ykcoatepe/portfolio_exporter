from __future__ import annotations

"""Tiny dev/ops helper to start PSD without exposing a CLI command.

Usage (systemd/launchd or manual):
    python scripts/psd_start.py
"""

from psd.runner import start_psd  # type: ignore


def main() -> None:
    start_psd()


if __name__ == "__main__":  # pragma: no cover
    main()

