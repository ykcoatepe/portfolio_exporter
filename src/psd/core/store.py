"""Minimal SQLite-backed store helpers for PSD runtime state."""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

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

            CREATE TABLE IF NOT EXISTS msb_readings (
                date TEXT PRIMARY KEY,
                hy REAL NOT NULL,
                vx1 REAL NOT NULL,
                vx2 REAL NOT NULL,
                z_hy REAL,
                term_ratio REAL,
                cal_spread_pct REAL,
                cal_spread_abs REAL,
                saturated INTEGER NOT NULL,
                hy_score INTEGER NOT NULL,
                vix_score INTEGER NOT NULL,
                msb INTEGER NOT NULL,
                color TEXT NOT NULL,
                triggers TEXT NOT NULL,
                winsor_clipped_n INTEGER NOT NULL,
                cooldown_until TEXT
            );
            """
        )
        conn.commit()
    raw_pages = os.getenv(
        "PSD_WAL_AUTOCHECKPOINT", str(_DEFAULT_AUTOCHECKPOINT_PAGES)
    ).strip()
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


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result:  # NaN guard
        return None
    return result


def _normalize_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=UTC)
        except (OverflowError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text.rstrip("Z") + "+00:00"
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None
    return None


def _legs_from_combo(combo: dict[str, Any]) -> list[dict[str, Any]]:
    legs = combo.get("legs")
    if isinstance(legs, list):
        return [leg for leg in legs if isinstance(leg, dict)]
    return []


def _collect_positions_view(view: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(view, dict):
        return [], [], []
    stocks = view.get("single_stocks")
    combos = view.get("option_combos")
    singles = view.get("single_options")
    stocks_list = [row for row in stocks if isinstance(row, dict)] if isinstance(stocks, list) else []
    combos_list = [row for row in combos if isinstance(row, dict)] if isinstance(combos, list) else []
    singles_list = [row for row in singles if isinstance(row, dict)] if isinstance(singles, list) else []
    return stocks_list, combos_list, singles_list


def _compute_leg_unrealized(leg: dict[str, Any]) -> float | None:
    mark = _coerce_float(
        leg.get("mark")
        or leg.get("price")
        or leg.get("marketPrice")
        or leg.get("lastPrice")
    )
    avg_cost = _coerce_float(leg.get("avg_cost") or leg.get("avgCost") or leg.get("cost_basis"))
    qty = _coerce_float(leg.get("qty") or leg.get("quantity") or leg.get("position"))
    multiplier = _coerce_float(leg.get("multiplier"))
    if multiplier is None:
        sec_type = str(leg.get("secType") or leg.get("sectype") or "").upper()
        multiplier = 100.0 if sec_type in {"OPT", "FOP"} else 1.0
    if mark is None or avg_cost is None or qty is None:
        return None
    return (mark - avg_cost) * qty * multiplier


def _sum_combo_greek(combo: dict[str, Any], greek: str) -> float | None:
    greeks = combo.get("greeks_agg")
    value = None
    if isinstance(greeks, dict):
        value = _coerce_float(greeks.get(greek))
    if value is not None:
        return value
    legs = _legs_from_combo(combo)
    total = 0.0
    has_value = False
    for leg in legs:
        leg_greeks = leg.get("greeks")
        if isinstance(leg_greeks, dict):
            leg_value = _coerce_float(leg_greeks.get(greek))
        else:
            leg_value = None
        if leg_value is None:
            continue
        total += leg_value
        has_value = True
    return total if has_value else None


def read_last_stats() -> dict[str, Any] | None:
    """Return the most recent persisted portfolio stats across sessions."""

    snapshot = latest_snapshot()
    if not isinstance(snapshot, dict):
        return None

    stats_source = snapshot.get("stats")
    stats_raw = stats_source if isinstance(stats_source, dict) else {}

    def _extract_number(*keys: str) -> float | None:
        for key in keys:
            if key in stats_raw:
                value = _coerce_float(stats_raw.get(key))
                if value is not None:
                    return value
        return None

    day_pnl = _extract_number("day_pnl", "dayPnl")
    unrealized_pnl = _extract_number("unrealized_pnl", "total_unrealized", "totalPnl")
    sigma_total = _extract_number("sigma_total", "sum_delta", "sumDelta")
    sigma_per_day = _extract_number("sigma_per_day", "sum_theta", "sumTheta")
    net_liq = _extract_number("net_liq", "netLiq")
    var_95 = _extract_number("var_95", "var95", "var95_1d", "var95_1d_pct")
    margin_pct = _extract_number("margin_pct", "marginPct", "margin_used_pct")

    view = snapshot.get("positions_view")
    stocks, combos, singles = _collect_positions_view(view)

    totals = {
        "day": 0.0,
        "unrealized": 0.0,
        "delta": 0.0,
        "theta": 0.0,
    }
    counts = {"day": 0, "unrealized": 0, "delta": 0, "theta": 0}

    for stock in stocks:
        day_value = _coerce_float(stock.get("day_pnl") or stock.get("pnl_intraday"))
        if day_value is not None:
            totals["day"] += day_value
            counts["day"] += 1
        unreal_value = _coerce_float(
            stock.get("pnl_unrealized")
            or stock.get("total_pnl")
            or stock.get("unrealized_pnl")
        )
        if unreal_value is None:
            unreal_value = _compute_leg_unrealized(stock)
        if unreal_value is not None:
            totals["unrealized"] += unreal_value
            counts["unrealized"] += 1
        greeks = stock.get("greeks")
        if isinstance(greeks, dict):
            delta_val = _coerce_float(greeks.get("delta"))
            if delta_val is not None:
                totals["delta"] += delta_val
                counts["delta"] += 1
            theta_val = _coerce_float(greeks.get("theta"))
            if theta_val is not None:
                totals["theta"] += theta_val
                counts["theta"] += 1

    for combo in combos:
        day_value = _coerce_float(combo.get("pnl_intraday") or combo.get("day_pnl"))
        if day_value is not None:
            totals["day"] += day_value
            counts["day"] += 1
        legs = _legs_from_combo(combo)
        leg_total = 0.0
        has_leg_total = False
        for leg in legs:
            leg_unreal = _compute_leg_unrealized(leg)
            if leg_unreal is None:
                continue
            leg_total += leg_unreal
            has_leg_total = True
        if has_leg_total:
            totals["unrealized"] += leg_total
            counts["unrealized"] += 1
        delta_val = _sum_combo_greek(combo, "delta")
        if delta_val is not None:
            totals["delta"] += delta_val
            counts["delta"] += 1
        theta_val = _sum_combo_greek(combo, "theta")
        if theta_val is not None:
            totals["theta"] += theta_val
            counts["theta"] += 1

    for single in singles:
        day_value = _coerce_float(single.get("pnl_intraday") or single.get("day_pnl"))
        if day_value is not None:
            totals["day"] += day_value
            counts["day"] += 1
        unreal_value = _compute_leg_unrealized(single)
        if unreal_value is not None:
            totals["unrealized"] += unreal_value
            counts["unrealized"] += 1
        greeks = single.get("greeks")
        if isinstance(greeks, dict):
            delta_val = _coerce_float(greeks.get("delta"))
            if delta_val is not None:
                totals["delta"] += delta_val
                counts["delta"] += 1
            theta_val = _coerce_float(greeks.get("theta"))
            if theta_val is not None:
                totals["theta"] += theta_val
                counts["theta"] += 1

    if day_pnl is None and counts["day"] > 0:
        day_pnl = totals["day"]
    if unrealized_pnl is None and counts["unrealized"] > 0:
        unrealized_pnl = totals["unrealized"]
    if sigma_total is None and counts["delta"] > 0:
        sigma_total = totals["delta"]
    if sigma_per_day is None and counts["theta"] > 0:
        sigma_per_day = totals["theta"]

    risk = snapshot.get("risk") if isinstance(snapshot.get("risk"), dict) else {}
    if net_liq is None:
        net_liq = _coerce_float(snapshot.get("net_liq") or snapshot.get("netLiq"))
    if net_liq is None and isinstance(risk, dict):
        net_liq = _coerce_float(risk.get("net_liq") or risk.get("notional"))
    if var_95 is None and isinstance(risk, dict):
        var_95 = _coerce_float(
            risk.get("var95_1d")
            or risk.get("var95")
            or risk.get("var_95")
            or risk.get("var95_1d_pct")
        )
    if margin_pct is None and isinstance(risk, dict):
        margin_pct = _coerce_float(
            risk.get("margin_pct")
            or risk.get("margin_used_pct")
            or risk.get("margin")
        )

    updated_at_raw = stats_raw.get("updated_at") or stats_raw.get("updatedAt")
    if updated_at_raw is None:
        updated_at_raw = snapshot.get("updated_at") or snapshot.get("updatedAt")
    if updated_at_raw is None:
        updated_at_raw = snapshot.get("ts")
    updated_dt = _normalize_timestamp(updated_at_raw)
    updated_at = updated_dt.isoformat() if updated_dt is not None else None

    data_source_raw = stats_raw.get("data_source") or stats_raw.get("dataSource")
    if data_source_raw is None:
        data_source_raw = snapshot.get("data_source") or snapshot.get("dataSource")
    data_source = (
        data_source_raw.strip() if isinstance(data_source_raw, str) and data_source_raw.strip() else None
    )

    session_raw = stats_raw.get("session") if isinstance(stats_raw, dict) else None
    session = session_raw if isinstance(session_raw, dict) else snapshot.get("session")
    session_info_raw = stats_raw.get("session_info") if isinstance(stats_raw, dict) else None
    session_info = session_info_raw if isinstance(session_info_raw, dict) else snapshot.get("session_info")

    values = [day_pnl, unrealized_pnl, sigma_total, sigma_per_day, net_liq, var_95, margin_pct]
    if all(value is None for value in values) and updated_at is None:
        return None

    return {
        "day_pnl": day_pnl,
        "unrealized_pnl": unrealized_pnl,
        "sigma_total": sigma_total,
        "sigma_per_day": sigma_per_day,
        "net_liq": net_liq,
        "var_95": var_95,
        "margin_pct": margin_pct,
        "updated_at": updated_at,
        "session": session if isinstance(session, dict) else None,
        "session_info": session_info if isinstance(session_info, dict) else None,
        "data_source": data_source,
    }


def latest_health() -> dict[str, Any] | None:
    """Return the most recent health row with connection state and data age."""
    row = None
    with _connect() as conn:
        try:
            row = conn.execute(
                """
                SELECT ts, ibkr_connected, data_age_s
                FROM health
                ORDER BY ts DESC
                LIMIT 1
                """
            ).fetchone()
        except sqlite3.OperationalError:
            try:
                row = conn.execute(
                    """
                    SELECT strftime('%s', updated_at) AS ts, ibkr_connected, data_age_s
                    FROM health
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """
                ).fetchone()
            except sqlite3.OperationalError:
                return None
    if not row:
        return None

    keys = row.keys() if hasattr(row, "keys") else []

    def _get_value(name: str, index: int | None = None) -> Any:
        if name in keys:
            return row[name]
        if index is not None:
            try:
                return row[index]
            except (IndexError, KeyError, TypeError):
                return None
        return None

    ts_raw = _get_value("ts", 0)
    try:
        ts_value = float(ts_raw) if ts_raw is not None else None
    except (TypeError, ValueError):
        ts_value = None

    ibkr_raw = _get_value("ibkr_connected", 1)
    ibkr_value = bool(ibkr_raw) if ibkr_raw is not None else False

    data_age_raw = _get_value("data_age_s", 2)
    try:
        data_age_value = float(data_age_raw)
    except (TypeError, ValueError):
        return None

    return {
        "ts": ts_value,
        "ibkr_connected": ibkr_value,
        "data_age_s": data_age_value,
    }


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


def tail_events(
    last_id: int = 0, limit: int = 200
) -> list[tuple[int, str, dict[str, Any]]]:
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
            (int(row["id"]), row["kind"], json.loads(row["payload"])) for row in rows
        ]
    return result


def max_event_id() -> int:
    """Return the current ledger head id (0 when empty).

    The SSE stream uses this to resume strictly after the bootstrap snapshot so
    reconnects never replay older snapshots.
    """
    with _connect() as conn:
        row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM events").fetchone()
    if not row:
        return 0
    try:
        return int(row[0])
    except (TypeError, ValueError):  # pragma: no cover - defensive fallback
        return 0


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


def store_msb(df: pd.DataFrame) -> int:
    """Persist MSB readings via upsert; returns affected row count."""
    if df.empty:
        return 0
    expected_columns = {
        "hy",
        "vx1",
        "vx2",
        "z_hy",
        "term_ratio",
        "cal_spread_pct",
        "cal_spread_abs",
        "saturated",
        "hy_score",
        "vix_score",
        "msb",
        "color",
        "triggers",
        "winsor_clipped_n",
        "cooldown_until",
    }
    missing = expected_columns.difference(df.columns)
    if missing:
        missing_sorted = ", ".join(sorted(missing))
        raise ValueError(f"Missing MSB columns: {missing_sorted}")

    records = []
    frame = df.sort_index().reset_index()
    for row in frame.itertuples(index=False):
        current_date = pd.Timestamp(row.date).date().isoformat()
        cooldown_raw = getattr(row, "cooldown_until", None)
        if pd.notna(cooldown_raw):
            cooldown_value = pd.Timestamp(cooldown_raw).date().isoformat()
        else:
            cooldown_value = None
        triggers_value = list(getattr(row, "triggers", []))
        triggers_encoded = json.dumps(triggers_value, separators=_JSON_SEPARATORS)
        records.append(
            (
                current_date,
                float(row.hy),
                float(row.vx1),
                float(row.vx2),
                None if pd.isna(row.z_hy) else float(row.z_hy),
                None if pd.isna(row.term_ratio) else float(row.term_ratio),
                None if pd.isna(row.cal_spread_pct) else float(row.cal_spread_pct),
                None if pd.isna(row.cal_spread_abs) else float(row.cal_spread_abs),
                int(bool(row.saturated)),
                int(row.hy_score),
                int(row.vix_score),
                int(row.msb),
                str(row.color),
                triggers_encoded,
                int(row.winsor_clipped_n),
                cooldown_value,
            )
        )
    with _connect() as conn:
        conn.executemany(
            """
            INSERT INTO msb_readings (
                date, hy, vx1, vx2, z_hy, term_ratio, cal_spread_pct, cal_spread_abs,
                saturated, hy_score, vix_score, msb, color, triggers,
                winsor_clipped_n, cooldown_until
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            ON CONFLICT(date) DO UPDATE SET
                hy=excluded.hy,
                vx1=excluded.vx1,
                vx2=excluded.vx2,
                z_hy=excluded.z_hy,
                term_ratio=excluded.term_ratio,
                cal_spread_pct=excluded.cal_spread_pct,
                cal_spread_abs=excluded.cal_spread_abs,
                saturated=excluded.saturated,
                hy_score=excluded.hy_score,
                vix_score=excluded.vix_score,
                msb=excluded.msb,
                color=excluded.color,
                triggers=excluded.triggers,
                winsor_clipped_n=excluded.winsor_clipped_n,
                cooldown_until=excluded.cooldown_until
            """,
            records,
        )
        conn.commit()
    return len(records)


def _decode_triggers(raw: str | bytes | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    if isinstance(data, list):
        return [str(item) for item in data]
    return []


def _normalize_msb_row(row: sqlite3.Row) -> dict[str, Any]:
    def _maybe_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    return {
        "date": str(row["date"]),
        "hy": float(row["hy"]),
        "vx1": float(row["vx1"]),
        "vx2": float(row["vx2"]),
        "z_hy": _maybe_float(row["z_hy"]),
        "term_ratio": _maybe_float(row["term_ratio"]),
        "cal_spread_pct": _maybe_float(row["cal_spread_pct"]),
        "cal_spread_abs": _maybe_float(row["cal_spread_abs"]),
        "saturated": bool(row["saturated"]),
        "hy_score": int(row["hy_score"]),
        "vix_score": int(row["vix_score"]),
        "msb": int(row["msb"]),
        "color": str(row["color"]),
        "triggers": _decode_triggers(row["triggers"]),
        "winsor_clipped_n": int(row["winsor_clipped_n"]),
        "cooldown_until": (
            str(row["cooldown_until"]) if row["cooldown_until"] is not None else None
        ),
    }


def read_msb_current() -> dict[str, Any] | None:
    """Return the most recent MSB reading if one exists."""
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT
                date,
                hy,
                vx1,
                vx2,
                z_hy,
                term_ratio,
                cal_spread_pct,
                cal_spread_abs,
                saturated,
                hy_score,
                vix_score,
                msb,
                color,
                triggers,
                winsor_clipped_n,
                cooldown_until
            FROM msb_readings
            ORDER BY date DESC
            LIMIT 1
            """
        ).fetchone()
    if row is None:
        return None
    return _normalize_msb_row(row)


def read_msb_history(days: int = 365) -> list[dict[str, Any]]:
    """Return up to ``days`` MSB readings ordered by descending date."""
    try:
        limit = int(days)
    except (TypeError, ValueError):
        limit = 0
    if limit <= 0:
        return []
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                date,
                hy,
                vx1,
                vx2,
                z_hy,
                term_ratio,
                cal_spread_pct,
                cal_spread_abs,
                saturated,
                hy_score,
                vix_score,
                msb,
                color,
                triggers,
                winsor_clipped_n,
                cooldown_until
            FROM msb_readings
            ORDER BY date DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_normalize_msb_row(row) for row in rows]
