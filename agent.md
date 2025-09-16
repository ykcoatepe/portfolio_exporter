# Portfolio Sentinel Dashboard (PSD)

- Quickstart: run `make psd-run` to print the scaffold message.
- Structure/Naming: sources live under `src/psd/**` (modules use snake_case; packages have `__init__.py` and a README.md placeholder).
- Dev Commands: use `make psd-*` targets (`psd-run`, `psd-scan-once`, `psd-dash`) and `make sanity-fast` for a quick Ruff+pytest pass.
- CI Gate: keep lint clean (ruff returns 0) and tests green before PR. No network I/O in tests.
- Troubleshooting: IBKR/YF credentials are not required for this scaffold; if later needed, ensure env is configured and clear caches (`.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`) when in doubt.
- Access: Menu → Portfolio Sentinel → opens the live dashboard. Auto-start runs once per session (web + browser + loop). Disable via `psd.auto.start_on_menu: false`.

## Browser

- Menu-only UX: there is no public CLI for PSD. Use the menu’s `o = Open in browser` action to start on demand when auto-start is disabled.
- Ops: for systemd/launchd, invoke `python scripts/psd_start.py`.
- Configure defaults under `config/rules.yaml` → `psd.auto`.
