#!/usr/bin/env bash
set -euo pipefail

ROOT=$(git rev-parse --show-toplevel)
LOG="$ROOT/debug/psd_logs.txt"

section() {
  printf '\n## %s\n' "$1" | tee -a "$LOG"
}

run_cmd() {
  local label=$1
  shift
  section "$label"
  { "$@" 2>&1 || true; } | tee -a "$LOG"
}

run_cmd "make sanity-fast" make sanity-fast
run_cmd "pytest -q" pytest -q
run_cmd "pytest PSD regressions" pytest -q libs/py/positions_engine/tests/test_psd_regressions.py
run_cmd "npm test --prefix apps/web" npm test --prefix apps/web
run_cmd "npm test --prefix apps/web OptionLegs" npm test --prefix apps/web -- OptionLegsTable.test.tsx usePortfolioMetrics.test.tsx

section "avg_cost=0 reproduction"
PYTHONPATH="$ROOT/libs/py" python - <<'PY' | tee -a "$LOG"
from decimal import Decimal
from positions_engine.core.models import Instrument, InstrumentType, Position
from positions_engine.service.normalize import compute_equity_pnl_fields

instrument = Instrument(symbol="AAPL", instrument_type=InstrumentType.EQUITY)
position = Position(instrument=instrument, quantity=Decimal("10"), avg_cost=Decimal("0"))
mark = Decimal("210")
previous_close = Decimal("205")
print(f"avg_cost input: {position.avg_cost}")
print(f"mark: {mark}, previous_close: {previous_close}, quantity: {position.quantity}")
print(f"compute_equity_pnl_fields total_pnl => {compute_equity_pnl_fields(position, mark, previous_close)['total_pnl']}")
PY
