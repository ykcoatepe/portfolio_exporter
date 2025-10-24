## v0.1.1 — FRED toggle & Parquet export
- Updated MSB release to 0.1.1 with pypdf upgrade and new pyarrow backend; web build uses Vite 7.1.12.
- Added FRED HY-OAS fetcher (MSB_SOURCE=fred) with cached CSV refresh and scheduler/CLI wiring.
- Introduced `/msb/history.parquet` export plus consolidated exporter helper shared with CSV route.
- UI action box now offers both CSV and Parquet downloads for downstream analysis.

## v0.1.0 — Market Stress Barometer
- MSB analytics (HY z-score 252B / 63B fallback, rolling winsor [1–99%]).
- VIX term structure (ratio, calendar %/abs) + saturation; calibrated scoring.
- REST: /msb/current, /msb/history(.csv); SSE: msb.update.
- TRT 17:30 scheduler; Sentinel Rules A/B/C (5B cooldown) + CSV audit.
- Live Status Bar writer; Prometheus metrics.
- UI: MSB card + mini-charts + action box; CSV export.
- Docs: Playbook rule, agent quickstart; CI: web-test gate; test-mode hardening.
