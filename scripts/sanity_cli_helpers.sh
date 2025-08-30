#!/usr/bin/env bash
set -euo pipefail
ok(){ printf "\033[32mPASS\033[0m %s\n" "$*"; }
die(){ printf "\033[31mFAIL\033[0m %s\n" "$*"; exit 1; }

# 0) Lint (optional)
if command -v ruff >/dev/null; then
  ruff check . || die "ruff failed"
  ok "ruff"
fi

# 1) Select Python interpreter
PY=${PYTHON:-python}
if ! command -v "$PY" >/dev/null 2>&1; then
  if command -v python3 >/dev/null 2>&1; then
    PY=python3
  else
    die "python not found; set PYTHON or install python3"
  fi
fi

# 2) Help screens expose common flags
"$PY" -m portfolio_exporter.scripts.trades_report -h \
  | grep -E -- '--json|--no-pretty|--no-files|--output-dir' >/dev/null \
  && ok "trades_report: common flags present" || die "trades_report missing common flags"

"$PY" -m portfolio_exporter.scripts.net_liq_history_export -h \
  | grep -E -- '--json|--no-pretty|--no-files|--output-dir' >/dev/null \
  && ok "netliq-export: common flags present" || die "netliq-export missing common flags"

"$PY" -m portfolio_exporter.scripts.daily_report -h \
  | grep -E -- '--json|--no-pretty|--no-files|--output-dir' >/dev/null \
  && ok "daily_report: common flags present" || die "daily_report missing common flags"

# daily_report should also advertise --excel
"$PY" -m portfolio_exporter.scripts.daily_report -h \
  | grep -E -- '--excel' >/dev/null \
  && ok "daily_report: --excel visible" || die "daily_report missing --excel"

# 3) JSON-only smokes (no files written)
PE_QUIET=1 "$PY" -m portfolio_exporter.scripts.trades_report \
  --executions-csv tests/data/executions_fixture.csv --json --no-files \
  | jq -e '.ok==true and (.outputs|length)==0' >/dev/null \
  && ok "trades_report: json-only ok" || die "trades_report json-only failed"

PE_QUIET=1 "$PY" -m portfolio_exporter.scripts.net_liq_history_export \
  --source fixture --fixture-csv tests/data/net_liq_fixture.csv --json --no-files \
  | jq -e '.ok==true and (.outputs|length)==0' >/dev/null \
  && ok "netliq-export: json-only ok" || die "netliq-export json-only failed"

OUTPUT_DIR=tests/data PE_QUIET=1 "$PY" -m portfolio_exporter.scripts.daily_report \
  --expiry-window 7 --json --no-files \
  | jq -e '.ok==true and (.outputs|length)==0' >/dev/null \
  && ok "daily_report: json-only ok" || die "daily_report json-only failed"

# 4) Drift test (if present)
if command -v pytest >/dev/null && [ -f tests/test_cli_flags_drift.py ]; then
  pytest -q tests/test_cli_flags_drift.py || die "pytest drift test failed"
  ok "pytest drift test"
fi

ok "PR-19 CLI helpers + drift sanity passed"
