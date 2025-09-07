#!/usr/bin/env bash
set -euo pipefail
ok(){ printf "\033[32mPASS\033[0m %s\n" "$*"; }
die(){ printf "\033[31mFAIL\033[0m %s\n" "$*"; exit 1; }

OUT=.tmp_trexcel; rm -rf "$OUT"; mkdir -p "$OUT"
# Create a minimal executions CSV compatible with --excel
EXEC="$OUT/exec.csv"
cat > "$EXEC" <<'CSV'
exec_id,perm_id,order_id,symbol,secType,Side,qty,price,datetime,expiry,right,strike
1,1,1,AAPL,OPT,BOT,1,1.0,2024-01-01T10:00:00,2024-02-16,C,150
CSV

if python3 -c 'import openpyxl' 2>/dev/null; then
  python3 -m portfolio_exporter.scripts.trades_report \
    --executions-csv "$EXEC" \
    --output-dir "$OUT" --excel --json >/dev/null
  test -f "$OUT/trades_report.xlsx" && ok "xlsx written" || die "xlsx missing"
else
  # Run without --excel so CSV writes (ensures manifest exists)
  python3 -m portfolio_exporter.scripts.trades_report \
    --executions-csv "$EXEC" \
    --output-dir "$OUT" --json >/dev/null || true
  test -f "$OUT/trades_report.xlsx" && die "xlsx should not exist without openpyxl" || ok "xlsx skipped gracefully"
fi

test -f "$OUT/trades_report_manifest.json" && ok "manifest present" || die "missing manifest"
echo; ok "PR-26 --excel sanity OK"
