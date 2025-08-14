# Roll Manager Dry-Run Enhancements

## Candidates
- V1: `--dry-run` flag with JSON preview and per-underlying limits.
- V2: Persist timings and manifest.
- V3: Integrate RunLog with optional `--debug-timings`.
- V4: Documentation and test coverage.

## Chosen Version
V1

## Tests / Smokes
- `pytest tests/test_roll_manager_cli.py`

## Follow-ups
- Consider richer warning collection and user feedback.
