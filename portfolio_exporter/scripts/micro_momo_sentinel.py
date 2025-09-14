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
from ..core.market_clock import rth_window_tr, is_after, pretty_tr, TZ_TR
from ..core.market_calendar import infer_close_et
from ..core.config_overlay import overlay_sentinel
from ..core.memory import load_memory


def _load_scored(path: str) -> List[Dict[str, Any]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _append_log(path: str, rows: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    write_header = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "ts",
                "symbol",
                "direction",
                "event",
                "price",
                "rvol",
                "event_type",
            ],
        )
        if write_header:
            w.writeheader()
        for r in rows:
            w.writerow(r)


def _side_vs_vwap(last_price: float | None, vwap: float | None) -> str | None:
    if last_price is None or vwap is None:
        return None
    try:
        return "above" if float(last_price) >= float(vwap) else "below"
    except Exception:
        return None


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
    cfg_sen_file = _load_sentinel_cfg(args.cfg)
    mem = {}
    try:
        m = load_memory()
        mem = (m.get("preferences", {}).get("sentinel", {}) or {})
    except Exception:
        mem = {}
    cfg_sen = overlay_sentinel(cfg_sen_file, mem)
    # Early close adjustment (ET), convert to TR via schedule builder
    dates_json = os.getenv("MOMO_SEN_EARLY_CLOSE_JSON") or (
        cfg_sen.get("early_close_dates_json") if isinstance(cfg_sen.get("early_close_dates_json"), str) else None
    )
    et_close_time = infer_close_et(dates_json=dates_json)
    et_rearm = _parse_hhmm(cfg_sen.get("et_afternoon_rearm", "13:30"))
    et_cutoff = _parse_hhmm(cfg_sen.get("et_no_new_signals_after", "15:30"))
    schedule = rth_window_tr(
        et_open=dt_time(9, 30),
        et_close=et_close_time,
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
    # Per-symbol runtime state
    state: Dict[str, Dict[str, Any]] = {}
    for row in scored:
        sym0 = row.get("symbol")
        if sym0:
            state[sym0] = {"fired": False, "cooldown": 0, "last_side": None, "last_bar_ts": None}
    # Post-halt single re-arm trackers
    post_halt_used: Dict[str, bool] = {row.get("symbol"): False for row in scored if row.get("symbol")}
    halts_seen: Dict[str, int] = {row.get("symbol"): 0 for row in scored if row.get("symbol")}
    last_halts_check = 0.0
    HALTS_POLL_SEC = 30
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
        # Halts polling (ET feed → convert to TR)
        now_ts = time.time()
        if cfg_sen.get("halt_rearm", True) and (now_ts - last_halts_check) >= HALTS_POLL_SEC:
            last_halts_check = now_ts
            try:
                from ..core.providers.halts_nasdaq import (
                    fetch_current_halts_csv,
                    parse_resume_events,
                )

                rows = fetch_current_halts_csv()
                resumes = parse_resume_events(rows)

                def _et_to_tr(et_hhmmss: str):
                    if not et_hhmmss:
                        return None
                    from zoneinfo import ZoneInfo
                    from datetime import datetime

                    now_ny = datetime.now(ZoneInfo("America/New_York"))
                    y, m, d = now_ny.year, now_ny.month, now_ny.day
                    parts = et_hhmmss.split(":")
                    if len(parts) < 2:
                        return None
                    hh = int(parts[0])
                    mm = int(parts[1])
                    ss = int(parts[2]) if len(parts) > 2 else 0
                    dt_ny = datetime(y, m, d, hh, mm, ss, tzinfo=ZoneInfo("America/New_York"))
                    return dt_ny.astimezone(TZ_TR)

                for sym, ev in resumes.items():
                    if sym not in state:
                        continue
                    if post_halt_used.get(sym):
                        continue
                    # skip if exceeded per-day max
                    if halts_seen.get(sym, 0) >= int(cfg_sen.get("max_halts_per_day", 1)):
                        continue
                    rq_tr = _et_to_tr(ev.get("resume_quote_et", ""))
                    if not rq_tr:
                        continue
                    # Apply schedule gates: only re-arm if before our TR cutoff and after open
                    if schedule.no_new_signals_after_tr and rq_tr >= schedule.no_new_signals_after_tr:
                        continue
                    if rq_tr < schedule.open_tr:
                        continue
                    st = state[sym]
                    st["fired"] = False
                    st["cooldown"] = 0
                    st["last_side"] = None
                    st["halt_rearm_not_before"] = rq_tr.timestamp() + int(
                        cfg_sen.get("halt_rearm_grace_sec", 45)
                    )
                    st["halt_mini_orb_bars_target"] = int(
                        cfg_sen.get("halt_mini_orb_minutes", 3)
                    )
                    st["halt_mini_orb_bars"] = 0
                    halts_seen[sym] = halts_seen.get(sym, 0) + 1
            except Exception:
                pass
        if (not armed_afternoon) and schedule.afternoon_rearm_tr and is_after(schedule.afternoon_rearm_tr):
            if cfg_sen.get("allow_afternoon_rearm", True):
                # simplest: allow one extra bite by clearing fired flags once
                fired = {}
                # Reset state to allow clean re-arm
                try:
                    for st in state.values():
                        st["fired"] = False
                        st["cooldown"] = 0
                        st["last_side"] = None
                except Exception:
                    pass
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
            bars: List[Dict[str, Any]] = []
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
            # Cooldown + VWAP recross gating
            st = state.setdefault(sym, {"fired": False, "cooldown": 0, "last_side": None, "last_bar_ts": None})
            # Decrement cooldown only on a new bar; also track mini-ORB bar accrual
            last_ts = None
            if bars:
                lb = bars[-1]
                last_ts = lb.get("ts") or lb.get("time") or lb.get("t") or lb.get("date")
            if last_ts is None:
                # Coarse fallback to minute clock if bars lack a timestamp field
                try:
                    last_ts = time.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    last_ts = None
            prev_ts = st.get("last_bar_ts")
            changed = prev_ts != last_ts
            if changed:
                if int(st.get("cooldown", 0)) > 0:
                    st["cooldown"] = max(0, int(st["cooldown"]) - 1)
                st["last_bar_ts"] = last_ts

            # Post-halt mini-ORB: wait grace + accrue bars before allowing evaluation
            if "halt_rearm_not_before" in st:
                if time.time() < float(st.get("halt_rearm_not_before", 0)):
                    continue
                if changed and bars:
                    st["halt_mini_orb_bars"] = int(st.get("halt_mini_orb_bars", 0)) + 1
                if int(st.get("halt_mini_orb_bars", 0)) < int(st.get("halt_mini_orb_bars_target", 0)):
                    continue

            side_now = _side_vs_vwap(snap.get("last"), vwap)
            # Gate 1: cooldown
            if int(st.get("cooldown", 0)) > 0:
                continue
            # Gate 2: VWAP recross
            if cfg_sen.get("require_vwap_recross", True):
                prev_side = st.get("last_side")
                if prev_side is None:
                    # On first observation, record the side but allow evaluation
                    # so tests and first-iteration triggers can fire when all
                    # other conditions are satisfied.
                    st["last_side"] = side_now
                elif side_now is None or side_now == prev_side:
                    continue
            ok = _check_trigger_long(snap, confirm, levels) if direction.startswith("long") else _check_trigger_short(snap, confirm, levels)
            # Remember the side evaluated on
            st["last_side"] = side_now
            if ok:
                fired[sym] = True
                st["fired"] = True
                if "halt_rearm_not_before" in st:
                    post_halt_used[sym] = True
                    for k in (
                        "halt_rearm_not_before",
                        "halt_mini_orb_bars_target",
                        "halt_mini_orb_bars",
                    ):
                        st.pop(k, None)
                event_type = "post_halt" if post_halt_used.get(sym) else "standard"
                logs.append(
                    {
                        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "symbol": sym,
                        "direction": direction,
                        "event": "TRIGGERED",
                        "price": snap.get("last"),
                        "rvol": snap.get("rvol"),
                        "event_type": event_type,
                    }
                )
                alerts.append(
                    {"symbol": sym, "direction": direction, "trigger": "Signal fired", "rvol_confirm": confirm, "levels": levels}
                )
                updates[sym] = {"status": "Triggered", "status_ts": time.strftime("%Y-%m-%d %H:%M:%S")}
            else:
                # Put on cooldown to avoid flapping
                try:
                    st["cooldown"] = max(0, int(cfg_sen.get("cooldown_bars", 10)))
                except Exception:
                    st["cooldown"] = 10
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
