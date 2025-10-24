## v0.1.0 — Market Stress Barometer
- MSB analytics (HY z-score 252B / 63B fallback, rolling winsor [1–99%]).
- VIX term structure (ratio, calendar %/abs) + saturation; calibrated scoring.
- REST: /msb/current, /msb/history(.csv); SSE: msb.update.
- TRT 17:30 scheduler; Sentinel Rules A/B/C (5B cooldown) + CSV audit.
- Live Status Bar writer; Prometheus metrics.
- UI: MSB card + mini-charts + action box; CSV export.
- Docs: Playbook rule, agent quickstart; CI: web-test gate; test-mode hardening.
