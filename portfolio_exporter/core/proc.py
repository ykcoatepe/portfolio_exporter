from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional


# PID files under out/.pid (created on import for convenience)
PID_DIR = Path("out/.pid")
PID_DIR.mkdir(parents=True, exist_ok=True)
META = PID_DIR / "momo_sentinel.meta.json"
PID = PID_DIR / "momo_sentinel.pid"


def _write_pidmeta(pid: int, argv: list[str], env: dict[str, str]) -> None:
    """Write lightweight metadata for the running process.

    Only whitelisted env keys are persisted for auditability.
    """
    env_keys = {
        "MOMO_SCORED",
        "MOMO_CFG",
        "MOMO_OUT",
        "MOMO_INTERVAL",
        "MOMO_WEBHOOK",
        "MOMO_THREAD",
        "MOMO_OFFLINE",
    }
    meta = {
        "pid": pid,
        "argv": argv,
        "env": {k: env[k] for k in env_keys if k in env},
        "started_at": int(time.time()),
    }
    META.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def is_running(pid: int) -> bool:
    """Return True if a process with PID appears to be alive.

    Prefers psutil when available; falls back to os.kill(pid, 0) on POSIX.
    """
    try:  # optional dependency
        import psutil  # type: ignore

        return psutil.pid_exists(pid) and (
            getattr(psutil.Process(pid), "status")() != getattr(psutil, "STATUS_ZOMBIE", "zombie")
        )
    except Exception:
        pass
    try:
        # On POSIX, signal 0 checks existence; on Windows it raises OSError if invalid
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def status() -> Dict[str, Any]:
    """Return current sentinel status with pid/meta if present."""
    if not PID.exists():
        return {"running": False, "reason": "pidfile missing"}
    try:
        pid = int(PID.read_text().strip())
    except Exception:
        return {"running": False, "reason": "invalid pidfile"}
    running = is_running(pid)
    meta: Dict[str, Any] = {}
    if META.exists():
        try:
            meta = json.loads(META.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    return {"running": running, "pid": pid, **meta}


def start(argv: list[str]) -> Dict[str, Any]:
    """Start the Micro‑MOMO sentinel as a detached background process.

    Returns {ok, pid} on success or {ok: False, msg} if already running.
    """
    if PID.exists():
        try:
            pid = int(PID.read_text().strip())
            if is_running(pid):
                return {"ok": False, "msg": f"already running (pid {pid})"}
        except Exception:
            pass

    # Launch detached process: python -m portfolio_exporter.scripts.micro_momo_sentinel ...
    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "portfolio_exporter.scripts.micro_momo_sentinel", *argv],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )
    PID.write_text(str(proc.pid), encoding="utf-8")
    _write_pidmeta(proc.pid, argv, dict(os.environ))
    return {"ok": True, "pid": proc.pid}


def stop(grace_seconds: int = 5) -> Dict[str, Any]:
    """Stop the sentinel gracefully (SIGTERM), then force kill if needed."""
    if not PID.exists():
        return {"ok": False, "msg": "not running"}
    try:
        pid = int(PID.read_text().strip())
    except Exception:
        return {"ok": False, "msg": "invalid pidfile"}

    # Try graceful terminate (equivalent to Popen.terminate / SIGTERM on POSIX)
    try:
        os.kill(pid, signal.SIGTERM)
    except Exception:
        pass

    t0 = time.time()
    while time.time() - t0 < max(1, grace_seconds):
        if not is_running(pid):
            _cleanup()
            return {"ok": True, "pid": pid, "msg": "terminated"}
        time.sleep(0.25)

    # Force kill as last resort
    try:
        sig = getattr(signal, "SIGKILL", signal.SIGTERM)
        os.kill(pid, sig)
    except Exception:
        pass
    _cleanup()
    return {"ok": True, "pid": pid, "msg": "killed"}


def _cleanup() -> None:
    try:
        PID.unlink(missing_ok=True)
        META.unlink(missing_ok=True)
    except Exception:
        pass

