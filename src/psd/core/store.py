"""Minimal SQLite-backed store helpers for PSD runtime state."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable

_JSON_SEPARATORS = (",", ":")
_VALID_CHECKPOINT_MODES = {"PASSIVE", "FULL", "RESTART", "TRUNCATE"}
_DEFAULT_AUTOCHECKPOINT_PAGES = 1000


def _db_path() -> Path:
    path = Path(os.environ.get("PSD_DB", "run/psd.db"))
    if not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;").fetchone()
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def _in_wal_mode(conn: sqlite3.Connection) -> bool:
    try:
        row = conn.execute("PRAGMA journal_mode;").fetchone()
    except sqlite3.OperationalError:
        return False
    if not row:
        return False
    mode = row[0]
    return str(mode).lower() == "wal"


def autocheckpoint(pages: int = 1000) -> None:
    """Configure automatic WAL checkpointing if journal mode allows it."""
    try:
        pages_int = int(pages)
    except (TypeError, ValueError):
        pages_int = _DEFAULT_AUTOCHECKPOINT_PAGES
    if pages_int <= 0:
        return
    with _connect() as conn:
        if not _in_wal_mode(conn):
            return
        try:
            conn.execute(f"PRAGMA wal_autocheckpoint={pages_int};")
        except sqlite3.OperationalError:
            return


def checkpoint(mode: str = "PASSIVE") -> None:
    """Trigger a WAL checkpoint in the requested mode when available."""
    mode_upper = mode.upper()
    if mode_upper not in _VALID_CHECKPOINT_MODES:
        raise ValueError(f"Unsupported checkpoint mode: {mode}")
    with _connect() as conn:
        if not _in_wal_mode(conn):
            return
        try:
            conn.execute(f"PRAGMA wal_checkpoint({mode_upper});")
        except sqlite3.OperationalError:
            return


def init() -> None:
    """Initialize schema and configure WAL defaults.

    Default WAL auto-checkpoint ~1000 pages (SQLite default); can still force PRAGMA wal_checkpoint.
    """
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                data TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                kind TEXT NOT NULL,
                payload TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS health (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                ibkr_connected INTEGER NOT NULL,
                data_age_s REAL NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.commit()
    raw_pages = os.getenv("PSD_WAL_AUTOCHECKPOINT", str(_DEFAULT_AUTOCHECKPOINT_PAGES)).strip()
    try:
        pages = int(raw_pages) if raw_pages else _DEFAULT_AUTOCHECKPOINT_PAGES
    except ValueError:
        pages = _DEFAULT_AUTOCHECKPOINT_PAGES
    autocheckpoint(pages)


def latest_snapshot() -> dict[str, Any] | None:
    """Return the most recent snapshot payload, if any."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT data FROM snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if row is None:
        return None
    return json.loads(row["data"])


def _json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=_JSON_SEPARATORS, sort_keys=True)


def write_snapshot(snap: dict[str, Any]) -> int:
    """Persist a snapshot and append a mirror event entry."""
    data = _json_dumps(snap)
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO snapshots (data) VALUES (?)",
            (data,),
        )
        snapshot_id = cur.lastrowid
        conn.commit()
    append_event("snapshot", snap)
    return int(snapshot_id)


def append_event(kind: str, payload: dict[str, Any]) -> int:
    """Append an event row and return its auto-increment id."""
    encoded = _json_dumps(payload)
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO events (kind, payload) VALUES (?, ?)",
            (kind, encoded),
        )
        event_id = cur.lastrowid
        conn.commit()
    return int(event_id)


def tail_events(last_id: int = 0, limit: int = 200) -> list[tuple[int, str, dict[str, Any]]]:
    """Return events newer than ``last_id`` up to ``limit`` rows."""
    with _connect() as conn:
        rows: Iterable[sqlite3.Row] = conn.execute(
            """
            SELECT id, kind, payload
            FROM events
            WHERE id > ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (last_id, limit),
        )
        result = [
            (int(row["id"]), row["kind"], json.loads(row["payload"]))
            for row in rows
        ]
    return result


def write_health(ibkr_connected: bool, data_age_s: float) -> None:
    """Record the latest health info and mirror it as an event."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO health (id, ibkr_connected, data_age_s, updated_at)
            VALUES (1, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                ibkr_connected=excluded.ibkr_connected,
                data_age_s=excluded.data_age_s,
                updated_at=CURRENT_TIMESTAMP
            """,
            (int(ibkr_connected), float(data_age_s)),
        )
        conn.commit()
    append_event(
        "health",
        {"ibkr_connected": bool(ibkr_connected), "data_age_s": float(data_age_s)},
    )
