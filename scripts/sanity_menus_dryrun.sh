#!/usr/bin/env bash
set -euo pipefail
ok(){ printf "\033[32mPASS\033[0m %s\n" "$*"; }
die(){ printf "\033[31mFAIL\033[0m %s\n" "$*"; exit 1; }

# Daily Report preview (JSON-only)
DAILY_REPORT_CMD="daily-report"
if ! command -v daily-report >/dev/null 2>&1; then
  PY_BIN="python"
  command -v "$PY_BIN" >/dev/null 2>&1 || PY_BIN="python3"
  DAILY_REPORT_CMD=($PY_BIN -m portfolio_exporter.scripts.daily_report)
fi
OUTPUT_DIR=tests/data PE_QUIET=1 ${DAILY_REPORT_CMD[@]} --expiry-window 7 --json --no-files \
  | jq -e '.ok==true and (.sections.positions!=null) and (.outputs|length)==0' >/dev/null \
  && ok "daily-report preview JSON-only" || die "daily-report preview failed"

# Roll Manager preview (JSON-only dry-run) with local positions stub
PY_BIN="python"; command -v "$PY_BIN" >/dev/null 2>&1 || PY_BIN="python3"
PE_QUIET=1 "$PY_BIN" - <<'PY' \
  | jq -e '.ok==true and (.sections.candidates>=0) and (.outputs|length)==0' >/dev/null \
  && ok "roll-manager dry-run preview JSON-only" || die "roll-manager preview failed"
import os, json, hashlib
import pandas as pd
from types import SimpleNamespace
from portfolio_exporter.scripts import roll_manager, portfolio_greeks
from portfolio_exporter.core import chain as chain_mod

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
async def _fake_load_positions():
    return pos_df

portfolio_greeks._load_positions = _fake_load_positions
portfolio_greeks.load_positions_sync = lambda: pos_df

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

echo; ok "menus dry-run wiring sanity (underlying previews) OK"
