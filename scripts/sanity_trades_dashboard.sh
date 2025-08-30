#!/usr/bin/env bash
set -euo pipefail

ok(){ printf "\033[32mPASS\033[0m %s\n" "$*"; }
die(){ printf "\033[31mFAIL\033[0m %s\n" "$*"; exit 1; }

command -v trades-dashboard >/dev/null || die "console entry 'trades-dashboard' not found"

# 1) JSON-only (no files)
PE_QUIET=1 trades-dashboard --json --no-files \
 | jq -e '.ok==true and .sections.clusters!=null and (.outputs|length)==0' >/dev/null \
 && ok "JSON-only summary" || die "json-only failed"

# 2) Files path (HTML + manifest; PDF optional)
OUT=.tmp_trdash; rm -rf "$OUT"; mkdir -p "$OUT"
OUTPUT_DIR=tests/data trades-dashboard --output-dir "$OUT" --json --debug-timings >/dev/null
test -f "$OUT/trades_dashboard.html" && ok "HTML written" || die "missing HTML"
test -f "$OUT/trades_dashboard_manifest.json" && ok "manifest written" || die "missing manifest"
if python -c 'import reportlab' 2>/dev/null; then
  test -f "$OUT/trades_dashboard.pdf" && ok "PDF written" || die "missing PDF"
else
  echo "note: reportlab not installed; PDF check skipped"
fi
test -f "$OUT/timings.csv" && ok "timings.csv written" || ok "timings.csv skipped (optional)"
echo; ok "Trades Dashboard sanity OK"

