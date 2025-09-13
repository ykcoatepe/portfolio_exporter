from __future__ import annotations

import argparse
import csv
import html
import os
from pathlib import Path
from typing import Any, Dict, List

CSS = (
    "body{font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:24px}"
    "h1{margin:0 0 16px 0}h2{margin:24px 0 8px 0}"
    ".table{border-collapse:collapse;width:100%;margin:8px 0 16px 0}"
    ".table th,.table td{border:1px solid #ddd;padding:6px 8px;font-size:13px}"
    ".badge{display:inline-block;padding:2px 8px;border-radius:12px;font-size:12px;color:#fff}"
    ".badge.A{background:#1b8e5a}.badge.B{background:#9b870c}.badge.C{background:#8b0000}"
    "kbd{background:#f4f4f4;border:1px solid #ddd;border-bottom-color:#ccc;border-radius:3px;padding:0.1em 0.4em}"
    ".small{color:#666;font-size:12px}"
    ".summary{margin:10px 0 18px 0}"
)


def _read_csv(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _summary(scored_rows: List[Dict[str, Any]]) -> str:
    """Build a compact summary header.

    - Totals by tier (A/B/C)
    - Provenance counts for VWAP source (artifact/yahoo/csv)
    - Guards: sum of concurrency_guard
    """
    n = len(scored_rows)
    a = sum(1 for r in scored_rows if (r.get("tier") or "").upper() == "A")
    b = sum(1 for r in scored_rows if (r.get("tier") or "").upper() == "B")
    # Treat anything not A/B as C for a quick snapshot
    c = max(0, n - a - b)

    srcs = [str(r.get("src_vwap", "")).lower() for r in scored_rows]
    src_art = sum(1 for s in srcs if s == "artifact")
    src_yf = sum(1 for s in srcs if s == "yahoo")
    src_csv = sum(1 for s in srcs if s == "csv")

    guards = 0
    for r in scored_rows:
        try:
            guards += int(float(r.get("concurrency_guard", 0) or 0))
        except Exception:
            continue

    return (
        "<div class='summary'>"
        f"<div>"
        f"<span class='badge A'>A: {a}</span> "
        f"<span class='badge B'>B: {b}</span> "
        f"<span class='badge C'>C: {c}</span> "
        f"<span class='badge' style='background:#555'>Guards: {guards}</span>"
        f"</div>"
        f"<div class='small'>VWAP src → artifact:{src_art} · yahoo:{src_yf} · csv:{src_csv}</div>"
        "</div>"
    )


def _section(title: str, rows: List[Dict[str, Any]], anchor: str) -> str:
    if not rows:
        return f"<h2 id='{html.escape(anchor)}'>{html.escape(title)}</h2><div class='small'>No data</div>"
    cols = list(rows[0].keys())
    wanted = [
        c
        for c in [
            "symbol",
            "tier",
            "direction",
            "structure",
            "contracts",
            "expiry",
            "long_leg",
            "short_leg",
            "tp",
            "sl",
            "entry_trigger",
            "status",
            "result_R",
        ]
        if c in cols
    ]
    seen = set(wanted)
    cols = wanted + [c for c in cols if c not in seen]
    head = "".join(f"<th>{html.escape(c)}</th>" for c in cols)
    body_rows: List[str] = []
    for r in rows:
        tds: List[str] = []
        for c in cols:
            val = r.get(c, "")
            if c == "tier" and val:
                tds.append(f"<td><span class='badge {html.escape(val)}'>{html.escape(val)}</span></td>")
            else:
                tds.append(f"<td>{html.escape(str(val))}</td>")
        body_rows.append("<tr>" + "".join(tds) + "</tr>")
    table = f"<table class='table'><thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"
    return f"<h2 id='{html.escape(anchor)}'>{html.escape(title)}</h2>" + table


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser("micro-momo-dashboard")
    ap.add_argument("--out_dir", default="out")
    args = ap.parse_args(argv)

    out = Path(args.out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)

    scored = _read_csv(out / "micro_momo_scored.csv")
    orders = _read_csv(out / "micro_momo_orders.csv")
    journal = _read_csv(out / "micro_momo_journal.csv")
    eod = _read_csv(out / "micro_momo_eod_summary.csv")
    triggers = _read_csv(out / "micro_momo_triggers_log.csv")

    html_doc = [
        "<!doctype html><meta charset='utf-8'><title>Micro-MOMO Dashboard</title>",
        f"<style>{CSS}</style>",
        "<h1>Micro-MOMO Dashboard</h1>",
        "<div class='small'>Sections: "
        "<a href='#scored'>Scored</a> · <a href='#orders'>Orders</a> · <a href='#journal'>Journal</a> · "
        "<a href='#eod-summary'>EOD Summary</a> · <a href='#trigger-log'>Trigger Log</a></div>",
        _summary(scored),
        _section("Scored", scored, "scored"),
        _section("Orders", orders, "orders"),
        _section("Journal", journal, "journal"),
        _section("EOD Summary", eod, "eod-summary"),
        _section("Trigger Log", triggers, "trigger-log"),
    ]
    (out / "micro_momo_dashboard.html").write_text("".join(html_doc), encoding="utf-8")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
