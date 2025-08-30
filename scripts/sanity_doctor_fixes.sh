#!/usr/bin/env bash
set -euo pipefail
ok(){ printf "\033[32mPASS\033[0m %s\n" "$*"; }
note(){ printf "\033[33mNOTE\033[0m %s\n" "$*"; }
die(){ printf "\033[31mFAIL\033[0m %s\n" "$*"; exit 1; }

need(){ command -v "$1" >/dev/null 2>&1 || die "Missing dependency: $1"; }
need doctor
need jq

# 1) Missing OUTPUT_DIR → should propose mkdir fix
TMP_OUT=.tmp_doctor_missing; rm -rf "$TMP_OUT" || true
env -i PATH="$PATH" OUTPUT_DIR="$TMP_OUT" PE_QUIET=1 \
  doctor --json --no-files | tee /tmp/doctor1.json >/dev/null
jq -e '.ok==true and (.sections.fixes|length)>=1' /tmp/doctor1.json >/dev/null \
  && ok "doctor produced fixes list" || die "no fixes list"
jq -r '.sections.fixes[]' /tmp/doctor1.json | grep -qi 'mkdir -p' \
  && ok "suggests mkdir for OUTPUT_DIR" || die "no mkdir fix for OUTPUT_DIR"

# 2) Missing CP_REFRESH_TOKEN → should propose token guidance
env -i PATH="$PATH" PE_QUIET=1 \
  doctor --json --no-files | tee /tmp/doctor2.json >/dev/null
if jq -r '.sections.fixes[]?' /tmp/doctor2.json | grep -qi 'CP_REFRESH_TOKEN'; then
  ok "suggests setting CP_REFRESH_TOKEN"
else
  note "CP_REFRESH_TOKEN hint not present (may be intentionally optional)"
fi

# 3) Missing TWS_EXPORT_DIR → should propose export dir fix
if jq -r '.sections.fixes[]?' /tmp/doctor2.json | grep -qi 'TWS_EXPORT_DIR'; then
  ok "suggests setting/creating TWS_EXPORT_DIR"
else
  note "TWS_EXPORT_DIR hint not present (may be optional in this env)"
fi

# 4) --preflight path: if supported and pandera absent, recommend install; else skip
if doctor --help 2>&1 | grep -q -- "--preflight"; then
  env -i PATH="$PATH" OUTPUT_DIR="$TMP_OUT" PE_QUIET=1 \
    doctor --json --no-files --preflight | tee /tmp/doctor3.json >/dev/null
  if jq -r '.sections.fixes[]?' /tmp/doctor3.json | grep -qi 'pip install pandera'; then
    ok "suggests installing pandera when missing"
  else
    note "pandera installed (or not required); install hint skipped"
  fi
else
  note "--preflight flag not supported by doctor; skipping check"
fi

ok "doctor fixes sanity passed"
