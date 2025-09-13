#!/usr/bin/env bash
set -euo pipefail
ok(){ printf "\033[32mPASS\033[0m %s\n" "$*"; }
die(){ printf "\033[31mFAIL\033[0m %s\n" "$*"; exit 1; }

# Find a Python interpreter
if command -v python >/dev/null 2>&1; then PY=python; 
elif command -v python3 >/dev/null 2>&1; then PY=python3; 
else die "python not found in PATH"; fi

# Three core presets → ticket present, ok:true
for P in bull_put bear_call iron_condor; do
  PE_QUIET=1 "$PY" -m portfolio_exporter.scripts.order_builder \
    --preset "$P" --symbol AAPL --expiry 2025-12-19 --qty 1 --json --no-files \
  | jq -e '.ok==true and (.ticket!=null)' >/dev/null || die "preset $P failed"
  ok "preset $P ticket"
done

# Calendar (date-only logic; still JSON-only)
PE_QUIET=1 "$PY" -m portfolio_exporter.scripts.order_builder \
  --preset calendar --symbol AAPL --expiry 2025-12-19 --qty 1 --json --no-files \
| jq -e '.ok==true and (.ticket!=null)' >/dev/null && ok "calendar preset ticket"

# Risk summary present when applicable (vertical/iron)
PE_QUIET=1 "$PY" -m portfolio_exporter.scripts.order_builder \
  --preset bull_put --symbol AAPL --expiry 2025-12-19 --qty 1 --json --no-files \
| jq -e '.risk_summary!=null and (.risk_summary.max_loss!=null)' >/dev/null && ok "risk summary populated"

echo; ok "order builder presets sanity OK"
