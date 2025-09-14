from __future__ import annotations

import argparse
import csv
import os
import time
from typing import Any, Dict, List

from ..core.alerts import emit_alerts
from ..core.journal import update_journal
from ..core.providers import ib_provider


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
    confirm = 1.3
    try:
        import json

        if args.cfg and os.path.exists(args.cfg):
            c = json.loads(open(args.cfg, encoding="utf-8").read())
            confirm = float(c.get("rvol_confirm_entry", c.get("targets", {}).get("rvol_confirm_entry", 1.3)))
    except Exception:
        pass

    fired: Dict[str, bool] = {}
    while True:
        logs: List[Dict[str, Any]] = []
        alerts: List[Dict[str, Any]] = []
        updates: Dict[str, Dict[str, Any]] = {}
        for row in scored:
            sym = row.get("symbol")
            direction = str(row.get("direction", "long"))
            if not sym or fired.get(sym):
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
