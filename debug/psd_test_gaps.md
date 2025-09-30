## Basis Missing (Cost Overwrite)
Given a PSD ingest snapshot that omits `avg_cost` for an equity
When `_derive_single_stock_rows` builds the row
Then unit coverage should assert the row preserves `avg_cost=None` and `compute_equity_pnl_fields` still emits non-null `total_pnl` once a mark is present.

Implemented checks:
- `libs/py/positions_engine/tests/test_psd_regressions.py::test_refresh_live_snapshot_preserves_existing_avg_cost`
- `libs/py/positions_engine/tests/test_psd_regressions.py::test_missing_basis_skips_total_pnl`

## Timestamp Propagation (Staleness)
Given an option leg payload whose quote arrives with `mark_source="LAST_CLOSE"` and a `previous_close_ts`
When `_normalize_option_mark_payload` transforms the entry
Then an integration test should verify the timestamp is retained and `_resolve_option_stale_seconds_entry` returns the real delta instead of the 86400-second fallback.

Implemented check:
- `libs/py/positions_engine/tests/test_psd_regressions.py::test_last_close_alias_preserves_timestamp`

## Leg Quote Rebuild
Given an option leg with quantity, avg_cost, and strategy metadata but no bid/ask/last fields
When `build_option_leg_snapshot` runs through combo detection
Then a regression test should synthesize a mid-price from previous close or greek hints so the resulting `OptionLegSnapshot` carries a usable mark and the UI can render the row.

Implemented checks:
- `libs/py/positions_engine/tests/test_psd_regressions.py::test_option_leg_rebuilds_mark_from_last_and_previous_close`
- `apps/web/src/components/OptionLegsTable.test.tsx::displays legs with derived marks even when totals are null`

## Portfolio Metrics Aggregation
Given a snapshot that includes legs with null P&L but valid marks
When `usePortfolioMetrics` computes aggregate totals
Then numeric legs should contribute to totals while rows with missing basis still appear in the view and retain staleness metadata.

Implemented check:
- `apps/web/src/hooks/usePortfolioMetrics.test.tsx::aggregates numeric totals while keeping legs with null P&L in the view`
