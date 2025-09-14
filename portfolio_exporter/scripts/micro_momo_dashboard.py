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
)


def _count_tiers(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    out: Dict[str, int] = {"A": 0, "B": 0, "C": 0}
    for r in rows:
        t = (r.get("tier") or "").strip()
        if t in out:
            out[t] += 1
    return out


def _count_provenance(rows: List[Dict[str, Any]], field: str = "src_vwap") -> Dict[str, int]:
    out: Dict[str, int] = {"artifact": 0, "yahoo": 0, "csv": 0, "": 0}
    for r in rows:
        v = (r.get(field) or "").strip().lower()
        if v in out:
            out[v] += 1
        else:
            out[""] += 1
    return out


def _sum_concurrency(rows: List[Dict[str, Any]]) -> int:
    s = 0
    for r in rows:
        try:
            s += int(r.get("concurrency_guard") or 0)
        except Exception:
            pass
    return s


def _summary_block(scored: List[Dict[str, Any]]) -> str:
    tiers = _count_tiers(scored)
    prov = _count_provenance(scored, "src_vwap")
    guards = _sum_concurrency(scored)
    html_parts = [
        "<div class='small' style='margin:6px 0 14px 0'>",
        f"Tiers: <span class='badge A'>A {tiers['A']}</span> · ",
        f"<span class='badge B'>B {tiers['B']}</span> · ",
        f"<span class='badge C'>C {tiers['C']}</span> &nbsp; ",
        "Provenance (VWAP): ",
        f"<kbd>artifact</kbd> {prov['artifact']} · ",
        f"<kbd>yahoo</kbd> {prov['yahoo']} · ",
        f"<kbd>csv</kbd> {prov['csv']} &nbsp; ",
        f"Guards: <kbd>concurrency_guard</kbd> {guards}",
        "</div>",
    ]
    return "".join(html_parts)


def _read_csv(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


    # (Note: _summary_block replaces the older _summary implementation.)


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

    summary = _summary_block(scored) if scored else "<div class='small'>No scored rows to summarize.</div>"

    html_doc = [
        "<!doctype html><meta charset='utf-8'><title>Micro-MOMO Dashboard</title>",
        f"<style>{CSS}</style>",
        "<h1>Micro-MOMO Dashboard</h1>",
        "<div class='small'>Sections: "
        "<a href='#scored'>Scored</a> · <a href='#orders'>Orders</a> · <a href='#journal'>Journal</a> · "
        "<a href='#eod-summary'>EOD Summary</a> · <a href='#trigger-log'>Trigger Log</a></div>",
        summary,
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
