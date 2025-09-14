from __future__ import annotations

from typing import Any, Dict, List


def _top_a(scored: List[Dict[str, Any]], n: int = 6) -> List[Dict[str, Any]]:
    a = [r for r in scored if (r.get("tier") == "A")]
    try:
        a.sort(key=lambda r: float(r.get("raw_score") or 0), reverse=True)
    except Exception:
        # If parsing fails, keep original order
        pass
    return a[:n]


def build_blocks(scored: List[Dict[str, Any]], published_dir: str) -> Dict[str, Any]:
    tiers = {"A": 0, "B": 0, "C": 0}
    for r in scored:
        t = (r.get("tier") or "").strip()
        if t in tiers:
            tiers[t] += 1
    title = f"Micro-MOMO — {tiers['A']} A  /  {tiers['B']} B  /  {tiers['C']} C"
    rows: List[str] = []
    for r in _top_a(scored):
        sym = r.get("symbol", "?")
        scr = r.get("raw_score", "")
        st = r.get("structure_template", "")
        lim = r.get("debit_or_credit", "")
        exp = r.get("expiry", "")
        rows.append(f"*{sym}*  {scr}  •  {st} {lim}  •  {exp}")
    tbl = "\n".join(rows) or "_No A-tier picks_"
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": title}},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Published*\n`{published_dir}`"},
                {"type": "mrkdwn", "text": "*Open locally*\n`make momo-dashboard-open`"},
            ],
        },
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Top A-tier*\n{tbl}"}},
    ]
    return {"blocks": blocks}

