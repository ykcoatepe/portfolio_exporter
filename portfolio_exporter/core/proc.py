from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

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


def status() -> dict[str, Any]:
    """Return current sentinel status with pid/meta if present."""
    if not PID.exists():
        return {"running": False, "reason": "pidfile missing"}
    try:
        pid = int(PID.read_text().strip())
    except Exception:
        return {"running": False, "reason": "invalid pidfile"}
    running = is_running(pid)
    meta: dict[str, Any] = {}
    if META.exists():
        try:
            meta = json.loads(META.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    return {"running": running, "pid": pid, **meta}


def start(argv: list[str]) -> dict[str, Any]:
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


def stop(grace_seconds: int = 5) -> dict[str, Any]:
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


# --------------------------
# Generic module proc helpers
# --------------------------
def start_module(pid_base: str, module: str, argv: list[str]) -> dict[str, Any]:
    """Start a python -m <module> with argv as a detached/background proc and write PID/meta.

    Uses per-module pid/meta files under out/.pid as <pid_base>.pid and <pid_base>.meta.json.
    """
    PID_DIR.mkdir(parents=True, exist_ok=True)
    pid_path = PID_DIR / f"{pid_base}.pid"
    meta_path = PID_DIR / f"{pid_base}.meta.json"

    if pid_path.exists():
        try:
            old = int(pid_path.read_text().strip())
            if is_running(old):
                return {"ok": False, "msg": f"{pid_base} already running (pid {old})"}
        except Exception:
            pass

    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", module, *argv],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )
    pid_path.write_text(str(proc.pid), encoding="utf-8")
    # Persist lightweight metadata with a small, auditable env snapshot
    env_keys = (
        "MOMO_SYMBOLS",
        "MOMO_CFG",
        "MOMO_OUT",
        "MOMO_PROVIDERS",
        "MOMO_DATA_MODE",
        "MOMO_FORCE_LIVE",
        "MOMO_OFFLINE",
        "MOMO_CACHE_TTL",
    )
    meta = {
        "pid": proc.pid,
        "module": module,
        "argv": argv,
        "env": {k: os.environ.get(k, "") for k in env_keys},
        "started_at": int(time.time()),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {"ok": True, "pid": proc.pid}


def status_module(pid_base: str) -> dict[str, Any]:
    """Return running status and meta for a generic module started via start_module."""
    pid_path = PID_DIR / f"{pid_base}.pid"
    meta_path = PID_DIR / f"{pid_base}.meta.json"
    if not pid_path.exists():
        return {"running": False, "reason": "pidfile missing"}
    try:
        pid = int(pid_path.read_text().strip())
    except Exception:
        return {"running": False, "reason": "invalid pidfile"}
    running = is_running(pid)
    meta: dict[str, Any] = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    return {"running": running, "pid": pid, **meta}


def start_module_logged(pid_base: str, module: str, argv: list[str], log_path: str) -> dict[str, Any]:
    """Start python -m <module> with argv; pipe stdout/stderr to log_path; write PID/meta.

    Writes pid/meta to out/.pid and ensures the log directory exists. Returns
    {ok, pid, log} or {ok: False, msg} if already running.
    """
    PID_DIR.mkdir(parents=True, exist_ok=True)
    pid_path = PID_DIR / f"{pid_base}.pid"
    meta_path = PID_DIR / f"{pid_base}.meta.json"

    if pid_path.exists():
        try:
            old = int(pid_path.read_text().strip())
            if is_running(old):
                return {"ok": False, "msg": f"{pid_base} already running (pid {old})"}
        except Exception:
            pass

    lp = Path(log_path)
    lp.parent.mkdir(parents=True, exist_ok=True)
    # Open in line-buffered text mode to stream logs
    log_f = open(lp, "a", buffering=1, encoding="utf-8")

    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", module, *argv],
        stdout=log_f,
        stderr=log_f,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )
    pid_path.write_text(str(proc.pid), encoding="utf-8")

    env_keys = (
        "MOMO_SYMBOLS",
        "MOMO_CFG",
        "MOMO_OUT",
        "MOMO_PROVIDERS",
        "MOMO_DATA_MODE",
        "MOMO_FORCE_LIVE",
        "MOMO_OFFLINE",
        "MOMO_CACHE_TTL",
    )
    meta = {
        "pid": proc.pid,
        "module": module,
        "argv": argv,
        "log": str(lp),
        "env": {k: os.environ.get(k, "") for k in env_keys},
        "started_at": int(time.time()),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return {"ok": True, "pid": proc.pid, "log": str(lp)}


def stop_module(pid_base: str, grace_seconds: int = 5) -> dict[str, Any]:
    """Stop a generic background module started via start_module/start_module_logged.

    Attempts graceful terminate, then force kill, and removes that module's pid/meta files.
    """
    pid_path = PID_DIR / f"{pid_base}.pid"
    meta_path = PID_DIR / f"{pid_base}.meta.json"
    if not pid_path.exists():
        return {"ok": False, "msg": "not running"}
    try:
        pid = int(pid_path.read_text().strip())
    except Exception:
        # clean up corrupted pid
        try:
            pid_path.unlink(missing_ok=True)
            meta_path.unlink(missing_ok=True)
        except Exception:
            pass
        return {"ok": False, "msg": "invalid pidfile"}

    try:
        os.kill(pid, signal.SIGTERM)
    except Exception:
        pass

    t0 = time.time()
    while time.time() - t0 < max(1, grace_seconds):
        if not is_running(pid):
            try:
                pid_path.unlink(missing_ok=True)
                meta_path.unlink(missing_ok=True)
            except Exception:
                pass
            return {"ok": True, "pid": pid, "msg": "terminated"}
        time.sleep(0.25)

    try:
        sig = getattr(signal, "SIGKILL", signal.SIGTERM)
        os.kill(pid, sig)
    except Exception:
        pass
    try:
        pid_path.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
    except Exception:
        pass
    return {"ok": True, "pid": pid, "msg": "killed"}
