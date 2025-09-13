# Menus dry-run wiring v1

Date: 2025-08-29 12:03 UTC

## Candidates
- Shell out to CLI scripts and parse JSON.
- Call Python entrypoints directly and silence UI with `PE_QUIET`.

## Decision
Chose direct entrypoints with a temporary `PE_QUIET` override to avoid spinners.
Added preview hooks for daily report and roll manager.
