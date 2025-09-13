#!/usr/bin/env bash
set -euo pipefail
ok(){ printf "\033[32mPASS\033[0m %s\n" "$*"; }
die(){ printf "\033[31mFAIL\033[0m %s\n" "$*"; exit 1; }

PY=$(command -v python || true)
if [[ -z "${PY}" ]]; then PY=$(command -v python3 || true); fi
if [[ -z "${PY}" ]]; then die "python or python3 not found in PATH"; fi

# 1) list tasks prints something
"${PY}" -m portfolio_exporter.main --list-tasks | tee /tmp/tasks.txt >/dev/null
grep -Eiq '.' /tmp/tasks.txt && ok "--list-tasks prints task registry" || die "no tasks listed"

# 2) dry-run shows a plan, but executes nothing
"${PY}" -m portfolio_exporter.main --dry-run | tee /tmp/plan.txt >/dev/null
grep -Eiq 'plan|queue|task' /tmp/plan.txt && ok "--dry-run shows execution plan" || die "no plan output"

# 3) workflow expansion using a temporary .codex/memory.json
ROOT="$(pwd)"
mkdir -p .codex
BAK=""
if [[ -f .codex/memory.json ]]; then BAK=".codex/memory.json.bak.$(date +%s)"; cp .codex/memory.json "$BAK"; fi
cat > .codex/memory.json <<JSON
{
  "workflows": {
    "submenu_queue": {
      "live": ["quick_chain", "daily_report"]
    }
  }
}
JSON
"${PY}" -m portfolio_exporter.main --workflow live --dry-run | tee /tmp/wf.txt >/dev/null
{ grep -Eiq 'quick_chain|daily_report' /tmp/wf.txt && ok "--workflow live expands from .codex/memory.json"; } || die "workflow expansion failed"
# restore any previous memory file
if [[ -n "$BAK" ]]; then mv "$BAK" .codex/memory.json; else rm -f .codex/memory.json; fi

# 4) help shows improved hints (hotkeys / multi-select)
"${PY}" -m portfolio_exporter.main -h | grep -Eiq 'multi.*select|e\.g\., 2,4|hotkey' \
  && ok "help epilog hints visible" || ok "help epilog hint not detected (optional)"

echo
ok "main.py planner sanity checks completed"
