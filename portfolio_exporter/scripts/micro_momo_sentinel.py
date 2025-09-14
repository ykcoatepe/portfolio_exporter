from __future__ import annotations

import argparse
import csv
import os
import time
from typing import Any, Dict, List, Optional
from datetime import time as dt_time

from ..core.alerts import emit_alerts
from ..core.journal import update_journal
from ..core.providers import ib_provider
from ..core.market_clock import rth_window_tr, is_after, pretty_tr


def _load_scored(path: str) -> List[Dict[str, Any]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _append_log(path: str, rows: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    write_header = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ts", "symbol", "direction", "event", "price", "rvol"])
        if write_header:
            w.writeheader()
        for r in rows:
            w.writerow(r)


def _load_sentinel_cfg(cfg_path: Optional[str]) -> dict:
    import json
    import os

    base = {
        "orb_minutes": 5,
        "single_fire": True,
        "allow_afternoon_rearm": True,
        "cooldown_bars": 10,
        "require_vwap_recross": True,
        "halt_rearm": True,
        "max_halts_per_day": 1,
        # anchors in ET (we’ll convert & DISPLAY in TR)
        "et_afternoon_rearm": "13:30",
        "et_no_new_signals_after": "15:30",
    }
    if cfg_path and os.path.exists(cfg_path):
        try:
            data = json.loads(open(cfg_path, encoding="utf-8").read())
            base.update((data.get("sentinel") or {}))
        except Exception:
            pass
    return base


def _parse_hhmm(s: str) -> dt_time:
    hh, mm = s.split(":")
    return dt_time(int(hh), int(mm))


def _check_trigger_long(snapshot: Dict[str, Any], confirm_rvol: float, levels: Dict[str, Any]) -> bool:
    # Simplified stateless check
    p = snapshot.get("last")
    vwap = levels.get("vwap")
    orb = levels.get("orb_high")
    rvol = float(snapshot.get("rvol", 0.0) or 0.0)
    if vwap and orb and p is not None:
        return (p >= orb) and (abs(p - vwap) / vwap <= 0.002 or p >= vwap) and (rvol >= confirm_rvol)
    return False


def _check_trigger_short(snapshot: Dict[str, Any], confirm_rvol: float, levels: Dict[str, Any]) -> bool:
    p = snapshot.get("last")
    vwap = levels.get("vwap")
    rvol = float(snapshot.get("rvol", 0.0) or 0.0)
    if vwap and p is not None:
        return (p <= vwap) and (rvol >= confirm_rvol)
    return False


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser("micro-momo-sentinel")
    ap.add_argument("--scored-csv", required=True)
    ap.add_argument("--cfg")
    ap.add_argument("--out_dir", default="out")
    ap.add_argument("--interval", type=int, default=10)
    ap.add_argument("--webhook")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--thread", help="Slack thread_ts for threaded alerts")
    args = ap.parse_args(argv)

    scored = _load_scored(args.scored_csv)
    # Load sentinel behavior knobs and compute today's TR-local schedule
    cfg_sen = _load_sentinel_cfg(args.cfg)
    et_rearm = _parse_hhmm(cfg_sen.get("et_afternoon_rearm", "13:30"))
    et_cutoff = _parse_hhmm(cfg_sen.get("et_no_new_signals_after", "15:30"))
    schedule = rth_window_tr(
        et_open=dt_time(9, 30),
        et_close=dt_time(16, 0),
        et_afternoon_rearm=et_rearm if cfg_sen.get("allow_afternoon_rearm", True) else None,
        et_no_new_after=et_cutoff,
    )
    # Log today's TR-local schedule
    print(
        f"[Sentinel schedule — TR] open: {pretty_tr(schedule.open_tr)}, "
        f"afternoon: {pretty_tr(schedule.afternoon_rearm_tr)}, "
        f"cutoff: {pretty_tr(schedule.no_new_signals_after_tr)}, "
        f"close: {pretty_tr(schedule.close_tr)}",
        flush=True,
    )
    confirm = 1.3
    try:
        import json

        if args.cfg and os.path.exists(args.cfg):
            c = json.loads(open(args.cfg, encoding="utf-8").read())
            confirm = float(c.get("rvol_confirm_entry", c.get("targets", {}).get("rvol_confirm_entry", 1.3)))
    except Exception:
        pass

    fired: Dict[str, bool] = {}
    cooldown: Dict[str, int] = {}
    armed_afternoon = False  # optional single re-arm flip in the afternoon
    while True:
        logs: List[Dict[str, Any]] = []
        alerts: List[Dict[str, Any]] = []
        updates: Dict[str, Dict[str, Any]] = {}
        # Time-based gates (TR-local)
        allow_new = True
        if schedule.no_new_signals_after_tr and is_after(schedule.no_new_signals_after_tr):
            # Hard “no-new” guard late day — do not ARM new names
            allow_new = False
        if (not armed_afternoon) and schedule.afternoon_rearm_tr and is_after(schedule.afternoon_rearm_tr):
            if cfg_sen.get("allow_afternoon_rearm", True):
                # simplest: allow one extra bite by clearing fired flags once
                fired = {}
            armed_afternoon = True
        for row in scored:
            sym = row.get("symbol")
            direction = str(row.get("direction", "long"))
            if not sym or fired.get(sym):
                continue
            if not allow_new:
                # Past the no-new guard; skip arming new names
                continue
            # snapshot via IB (tests can monkeypatch)
            snap = {"last": None, "rvol": 0.0}
            if not args.offline:
                try:
                    q = ib_provider.get_quote(sym, {"data": {"offline": False}})
                    snap["last"] = q.get("last")
                    bars = ib_provider.get_intraday_bars(sym, {"data": {"offline": False}}, minutes=5, prepost=True)
                    vol = sum(b.get("volume", 0) for b in bars[-5:])
                    avg = max(1, sum(b.get("volume", 1) for b in bars[-25:]) / 25)
                    snap["rvol"] = vol / avg
                except Exception:
                    pass

            vwap = float(row.get("vwap") or 0) or None
            orb = float(row.get("orb_high") or 0) or None
            levels = {"vwap": vwap, "orb_high": orb}
            ok = _check_trigger_long(snap, confirm, levels) if direction.startswith("long") else _check_trigger_short(snap, confirm, levels)
            if ok:
                fired[sym] = True
                logs.append(
                    {
                        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "symbol": sym,
                        "direction": direction,
                        "event": "TRIGGERED",
                        "price": snap.get("last"),
                        "rvol": snap.get("rvol"),
                    }
                )
                alerts.append(
                    {"symbol": sym, "direction": direction, "trigger": "Signal fired", "rvol_confirm": confirm, "levels": levels}
                )
                updates[sym] = {"status": "Triggered", "status_ts": time.strftime("%Y-%m-%d %H:%M:%S")}
        if logs:
            _append_log(os.path.join(args.out_dir, "micro_momo_triggers_log.csv"), logs)
            if args.webhook and not args.offline:
                if args.thread:
                    emit_alerts(
                        alerts,
                        args.webhook,
                        dry_run=False,
                        offline=False,
                        per_item=True,
                        extra={"thread_ts": args.thread},
                    )
                else:
                    emit_alerts(alerts, args.webhook, dry_run=False, offline=False)
            j = os.path.join(args.out_dir, "micro_momo_journal.csv")
            if os.path.exists(j):
                update_journal(j, updates)
        time.sleep(max(1, args.interval))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
