#!/usr/bin/env bash
set -euo pipefail

ok(){ printf "\033[32mPASS\033[0m %s\n" "$*"; }
die(){ printf "\033[31mFAIL\033[0m %s\n" "$*"; exit 1; }

# 1) JSON-only filtered by symbol + effect (no files)
PE_QUIET=1 python3 -m portfolio_exporter.scripts.trades_report \
  --executions-csv tests/data/executions_fixture.csv \
  --symbol AAPL --effect-in Close --json --no-files \
| jq -e '
  .ok==true and
  .sections.filtered.rows_count>=0 and
  (.outputs|length)==0 and
  (.meta.filters.symbol|contains(["AAPL"]))
' >/dev/null && ok "json-only filtered view" || die "json-only filtering failed"

# 2) Grouped view (by underlying)
PE_QUIET=1 python3 -m portfolio_exporter.scripts.trades_report \
  --executions-csv tests/data/executions_fixture.csv \
  --group-by underlying --json --no-files \
| jq -e '.ok==true and (.sections.grouped|type)=="array"' >/dev/null \
  && ok "grouped view in JSON" || die "grouped JSON missing"

# 3) Files path with structure filter + top-n (writes filtered CSVs)
OUT=.tmp_trfilters; rm -rf "$OUT"; mkdir -p "$OUT"
python3 -m portfolio_exporter.scripts.trades_report \
  --executions-csv tests/data/executions_fixture.csv \
  --structure-in condor --top-n 5 --output-dir "$OUT" --json --debug-timings >/dev/null

test -f "$OUT/trades_report_filtered.csv" && ok "rows filtered csv written" || die "missing trades_report_filtered.csv"
if test -f "$OUT/trades_clusters_filtered.csv"; then ok "clusters filtered csv written"; fi
test -f "$OUT/trades_report_manifest.json" && ok "manifest present" || die "missing manifest"

echo; ok "PR-25 trades_report filters sanity OK"
