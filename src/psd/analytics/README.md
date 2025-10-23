# PSD Analytics

## Analyzers
- `combos.recognize(positions)` matches verticals and iron condors, returning `Combo` dataclasses plus orphan warnings.
- `exposure.delta_beta_exposure(positions, nav)` combines equity beta and option delta exposure into a NAV-normalized scalar.
- `stats.compute_stats(snapshot)` summarizes positions, legs, combo counts, and quote staleness for the dashboard.
- `var.var95_1d_from_closes(closes, nav_exposed)` estimates 95% 1-day VaR using historical returns with a parametric fallback.
- `beta` keeps the import surface in place for upcoming factor analytics; current builds expose stubs so downstream wiring stays stable.

## Contracts
- `Combo.to_dict()` returns a JSON-safe payload consumed by the dashboard adapters and persisted in ledger/event logs.
- `compute_stats` produces a flat dictionary with the keys asserted in `tests/test_psd_stats.py` and streamed via `/stats`.
- Exposure and VaR helpers return primitive `float` values so callers control serialization and rounding.
- Analyzer modules avoid side effects on import and raise `ValueError` for invalid inputs to keep `psd.runtime` orchestration predictable.

## Performance Budgets
- Combo recognition should stay ≤5 ms for ≤200 option legs (profiled on M2/3.4 GHz-equivalent laptops); regressions get flagged in perf harness scripts.
- Stats computation targets ≤3 ms for 1 000 mixed positions so we can refresh the dashboard once per second without backlog.
- Exposure and VaR helpers run in ≤1 ms for typical day ranges (<1 000 legs, ≤252 closes) and short-circuit to 0 for empty inputs.
- Keep allocations minimal—prefer lists and tuples over NumPy to maintain deterministic runtimes in CI and serverless deployments.
