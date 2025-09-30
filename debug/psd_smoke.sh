#!/usr/bin/env bash

set -euo pipefail

echo "== Ruff =="
ruff check libs/py/positions_engine --fix

echo "== Unit tests (targeted) =="
pytest -q \
  libs/py/positions_engine/tests/test_staleness_mapping.py \
  libs/py/positions_engine/tests/test_option_leg_mark_fallback.py \
  libs/py/positions_engine/tests/test_avg_cost_guard.py

echo "== Basis sanity =="
python - <<'PY'
from decimal import Decimal

def pnl(mark, qty, avg):
    return None if avg in (None, 0) else (Decimal(mark) - Decimal(avg)) * Decimal(qty)

assert pnl(105, 10, Decimal("100")) == Decimal("50")
assert pnl(105, 10, None) is None
print("basis_ok")
PY

echo "All good."
