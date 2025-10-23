# PSD UI

## React Query Polling
- The root `QueryClient` lives in `apps/web/src/main.tsx` with stale times tuned per resource (`usePsdSnapshot`, `useRules`, `useStocks`).
- Hooks under `apps/web/src/hooks/` wrap `@tanstack/react-query` and fan out between REST polling and SSE-driven cache updates.
- Query keys follow the `["psd", "..."]` convention so cache invalidation is predictable across panels and tests reusable in `src/hooks/*test.tsx`.
- MSB widgets read from `/msb/current` and `/msb/history`, while `/sse` emits `msb.update` events with compact payloads for live dashboards.

## SPA Build
- `npm run build` (surfaced via `make web-build`) emits the production bundle into `apps/web/dist`.
- `apps/api/main.py` mounts the dist directory at `/psd`, and the fallback middleware serves `index.html` for unknown routes to support client-side routing.
- CI installs Node 20, runs `make web-build`, and fails fast if `apps/web/dist/index.html` is missing, keeping backend + frontend releases in lockstep.

## Mount Test
- `tests/test_spa_mount.py` boots the FastAPI app, asserts `/psd` serves HTML, and confirms API routes still respond while the SPA is mounted.
- The test guards against regressions where static mounting might shadow REST endpoints or ship stale assets—keeping it enabled requires building the SPA as part of CI.
- Local runs can reproduce the same contract by executing `make web-build` before `pytest -q tests/test_spa_mount.py`.
- Backend tests spin up the API with `create_app(Settings(test_mode=True, disable_background=True))` to skip background jobs and keep suites fast.
