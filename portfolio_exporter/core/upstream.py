from __future__ import annotations

"""
Lightweight upstream orchestrators for generating local artifacts.

All functions are best‑effort, timeout‑guarded, and return only True/False.
They should safely no‑op when required scripts are not available.

Tests can monkeypatch these functions to simulate successful generation and
to materialize tiny CSV artifacts for bars/chains.
"""

from typing import Iterable
import subprocess
import sys
import shlex


def _run(cmd: str, timeout: int) -> bool:
    try:
        # Use shell=False for safety; accept simple command strings
        proc = subprocess.run(shlex.split(cmd), timeout=timeout)
        return proc.returncode == 0
    except Exception:
        return False


def run_chain_snapshot(symbols: Iterable[str], timeout: int = 30) -> bool:
    """Attempt to generate option‑chain CSVs via in‑repo snapshot script.

    Safe no‑op if the script is missing or fails. Returns True on success.
    """
    syms = ",".join({s.strip().upper() for s in symbols if s and s.strip()})
    if not syms:
        return False
    # Prefer module entry first; fall back to repo‑root script
    cmds = [
        f"{shlex.quote(sys.executable)} -m portfolio_exporter.scripts.option_chain_snapshot --format csv --symbols {shlex.quote(syms)}",
        f"{shlex.quote(sys.executable)} option_chain_snapshot.py --format csv --symbols {shlex.quote(syms)}",
    ]
    for c in cmds:
        if _run(c, timeout=timeout):
            return True
    return False


def run_live_bars(symbols: Iterable[str], timeout: int = 30) -> bool:
    """Attempt to generate recent minute bars artifacts via in‑repo producer.

    This project does not mandate a specific bars producer. If none is
    available, the function safely returns False. Tests may monkeypatch this
    to emit tiny CSVs under a temp output directory.
    """
    # No standard producer present; return False by default. Keep signature
    # stable for monkeypatching in tests.
    return False


def run_tech_scan(symbols: Iterable[str], timeout: int = 30) -> bool:
    """Try to run a lightweight technical scan to produce a shortlist.

    Safe no‑op by default; returns False when unavailable. Agents may wire
    this to portfolio_exporter.scripts.tech_scan in the future.
    """
    try:
        from portfolio_exporter.scripts import tech_scan as _ts  # type: ignore

        _ts.run(tickers=list(symbols), fmt="csv")
        return True
    except Exception:
        return False

