#!/usr/bin/env bash
set -euo pipefail
ok(){ printf "\033[32mPASS\033[0m %s\n" "$*"; }
die(){ printf "\033[31mFAIL\033[0m %s\n" "$*"; exit 1; }

# 1) Generate a fresh daily-report HTML so "Open last report" has something to find
OUT_D=.tmp_daily_for_open; rm -rf "$OUT_D"; mkdir -p "$OUT_D"
OUTPUT_DIR=tests/data python3 -m portfolio_exporter.scripts.daily_report --expiry-window 7 --output-dir "$OUT_D" >/dev/null
test -f "$OUT_D/daily_report.html" || die "daily_report.html not created"

# 2) Resolve last report path via the menu helper (no browser open in quiet)
OUTPUT_DIR="$OUT_D" python3 - <<'PY'
from portfolio_exporter.menus import trade
p = trade._resolve_last_report(prefer="daily")
assert p and p.name.endswith("daily_report.html"), f"Unexpected path: {p}"
msg = trade.open_last_report(prefer="daily", quiet=True)
print("MSG:", msg)
PY
ok "resolve/open last report (quiet) prints path"

# 3) Save filtered trades CSV now (underlying helper)
OUT=.tmp_trquick; rm -rf "$OUT"; mkdir -p "$OUT"
python3 - <<'PY'
from pathlib import Path
import portfolio_exporter.scripts.trades_report as tr_mod
from portfolio_exporter.menus import trade

def fake_main(argv):
    Path(".tmp_trquick/trades_report_filtered.csv").write_text("dummy")
    return {"ok": True, "outputs": [".tmp_trquick/trades_report_filtered.csv"]}

tr_mod.main = fake_main
j = trade._quick_save_filtered(output_dir=".tmp_trquick", symbols="AAPL", effect_in="Close", top_n=5, quiet=True)
assert isinstance(j, dict) and j.get("ok", False), "quick_save_filtered did not return ok JSON"
PY
test -f ".tmp_trquick/trades_report_filtered.csv" && ok "filtered trades csv written" || die "missing filtered csv"

# 4) Copy JSON summary path — preview JSON is returned; clipboard optional
python3 - <<'PY'
from portfolio_exporter.menus import trade
import portfolio_exporter.scripts.trades_report as tr_mod

tr_mod.main = lambda argv: {"ok": True}
s = trade._preview_trades_json(symbols="AAPL", effect_in="Close", top_n=3)
assert isinstance(s, str) and '"ok":true' in s.replace(" ", "").lower(), "preview json not ok"
try:
    copied = trade._copy_to_clipboard("test")
    print("CLIPBOARD:", copied)
except Exception as e:
    print("CLIPBOARD_ERROR:", e)
PY
ok "preview json path ok (clipboard optional)"
echo; ok "Menus Quick Actions sanity OK"
