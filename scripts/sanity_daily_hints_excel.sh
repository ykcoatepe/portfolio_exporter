#!/usr/bin/env bash
set -euo pipefail
ok(){ printf "\033[32mPASS\033[0m %s\n" "$*"; }
die(){ printf "\033[31mFAIL\033[0m %s\n" "$*"; exit 1; }

command -v daily-report >/dev/null || die "console entry 'daily-report' not found"

# 1) JSON-only preflight on an empty dir → actionable warnings
TMP=.tmp_empty_dr; rm -rf "$TMP"; mkdir -p "$TMP"
OUTPUT_DIR="$TMP" PE_QUIET=1 daily-report --json --no-files --preflight \
  | tee /tmp/dr_pf.json >/dev/null
jq -e '.ok==true and (.warnings|length)>=1' /tmp/dr_pf.json >/dev/null \
  && ok "preflight produced warnings" || die "no warnings from preflight"
jq -r '.warnings[]' /tmp/dr_pf.json | grep -qi 'run: portfolio-greeks' \
  && ok "actionable hint mentions portfolio-greeks" || die "no actionable hint"

# 2) Defaults unchanged when writing files (HTML+PDF, no XLSX unless --excel)
OUT=.tmp_daily_defaults; rm -rf "$OUT"; mkdir -p "$OUT"
OUTPUT_DIR=tests/data daily-report --expiry-window 7 --output-dir "$OUT" >/dev/null
test -f "$OUT/daily_report.html" && ok "HTML written by default" || die "missing HTML"
if python -c 'import reportlab' 2>/dev/null; then
  test -f "$OUT/daily_report.pdf" && ok "PDF written by default" || die "missing PDF"
else
  echo "note: reportlab not installed; PDF check skipped"
fi
test -f "$OUT/daily_report.xlsx" && die "XLSX should NOT exist without --excel" || ok "No XLSX without --excel"

# 3) --excel behavior
OUT=.tmp_daily_excel; rm -rf "$OUT"; mkdir -p "$OUT"
if python -c 'import openpyxl' 2>/dev/null; then
  OUTPUT_DIR=tests/data daily-report --expiry-window 7 --output-dir "$OUT" --excel >/dev/null
  test -f "$OUT/daily_report.xlsx" && ok "XLSX written with --excel" || die "XLSX missing with --excel"
else
  OUTPUT_DIR=tests/data daily-report --expiry-window 7 --output-dir "$OUT" --excel >/dev/null || true
  test -f "$OUT/daily_report.xlsx" && die "XLSX should not be written without openpyxl" || ok "Graceful skip of XLSX when openpyxl missing"
fi

# 4) Help advertises the new flag
daily-report -h | grep -Eiq -- '--excel' && ok "--excel visible in -h" || die "--excel missing in help"

ok "PR-18 daily_report preflight + excel sanity OK"

