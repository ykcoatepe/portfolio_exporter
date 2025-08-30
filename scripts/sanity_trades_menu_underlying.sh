#!/usr/bin/env bash
set -euo pipefail
ok(){ printf "\033[32mPASS\033[0m %s\n" "$*"; }
die(){ printf "\033[31mFAIL\033[0m %s\n" "$*"; exit 1; }

# Resolve Python binary
PY_BIN="python"; command -v "$PY_BIN" >/dev/null 2>&1 || PY_BIN="python3"

# Always use module invocations to avoid PATH/entrypoint drift
DAILY_REPORT_CMD=($PY_BIN -m portfolio_exporter.scripts.daily_report)
TRADES_REPORT_CMD=($PY_BIN -m portfolio_exporter.scripts.trades_report)

# 1) Daily Report preview (JSON-only, no files)
OUTPUT_DIR=tests/data PE_QUIET=1 ${DAILY_REPORT_CMD[@]} --expiry-window 7 --json --no-files \
 | jq -e '.ok==true and (.sections.positions!=null) and (.outputs|length)==0' >/dev/null \
 && ok "daily-report preview JSON-only" || die "daily-report preview failed"

# 2) Daily Report preflight (JSON-only; should warn on empty dir)
TMP=.tmp_empty_dr; rm -rf "$TMP"; mkdir -p "$TMP"
OUTPUT_DIR="$TMP" PE_QUIET=1 ${DAILY_REPORT_CMD[@]} --json --no-files --preflight \
 | jq -e '.ok==true and (.warnings|length)>=1' >/dev/null \
 && ok "daily-report preflight warnings" || die "daily-report preflight missing warnings"

# 3) Roll Manager preview (JSON-only dry-run) with stub fallback
PE_QUIET=1 "$PY_BIN" - <<'PY' \
 | jq -e '.ok==true and (.sections.candidates>=0) and (.outputs|length)==0' >/dev/null \
 && ok "roll-manager dry-run preview (stub) JSON-only" || die "roll-manager preview failed"
import os, json, hashlib
import pandas as pd
from types import SimpleNamespace
from portfolio_exporter.scripts import roll_manager, portfolio_greeks

pos_csv = os.path.join('tests','data','portfolio_greeks_positions.csv')
df = pd.read_csv(pos_csv)

# Ensure required columns
if 'secType' not in df.columns:
    df['secType'] = 'OPT'

# Synthesize stable negative conIds
def synth_conid(row):
    key = f"{row.get('underlying','')}|{row.get('expiry','')}|{row.get('right','')}|{row.get('strike','')}"
    v = int.from_bytes(hashlib.sha1(key.encode()).digest()[:4], 'big')
    return -int(v)
df['conId'] = df.apply(synth_conid, axis=1)

# Minimal normalization
df['right'] = df['right'].astype(str).str.upper().str[0]
pos_df = df.set_index('conId')

# Monkeypatch loader
portfolio_greeks._load_positions = lambda: pos_df

# Stub option chain fetcher to avoid network/optional deps
def _fake_fetch_chain(symbol: str, expiry: str, strikes=None):
    if not strikes:
        strikes = []
    rows = []
    for k in strikes:
        for r in ('C','P'):
            rows.append({
                'strike': float(k),
                'right': r,
                'mid': 1.0,
                'bid': 0.9,
                'ask': 1.1,
                'delta': 0.2 if r=='C' else -0.2,
                'gamma': 0.01,
                'vega': 0.05,
                'theta': -0.01,
                'iv': 0.3,
            })
    return pd.DataFrame(rows)
roll_manager.fetch_chain = _fake_fetch_chain

args = SimpleNamespace(
    include_cal=False,
    days=7,
    tenor='all',
    limit_per_underlying=None,
    dry_run=True,
    debug_timings=False,
    no_pretty=True,
    json=True,
    output_dir=None,
    no_files=True,
)
summary = roll_manager.cli(args)
print(json.dumps(summary))
PY

# 4) Trades clusters preview (JSON-only) on fixture executions
PE_QUIET=1 ${TRADES_REPORT_CMD[@]} --executions-csv tests/data/executions_fixture.csv --json --no-files \
 | jq -e '.ok==true and (.sections.clusters!=null)' >/dev/null \
 && ok "trades-report clusters preview" || die "trades-report preview failed"

echo; ok "Trades & Reports menu underlying previews OK"
