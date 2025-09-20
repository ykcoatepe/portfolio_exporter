# Vite/Vitest Major Upgrade Plan (Draft)

_Last updated: 2025-09-20 · Owner: web tooling_

## Goal
Prepare for the next Vite/Vitest major release (shipping the refreshed esbuild toolchain) so we can adopt it quickly without disrupting the web UI build or contract suite.

## Target versions
- `vite` → next major (expected 8.x; track the `beta`/`next` dist-tags)
- `vitest` → matching major (expected 4.x)
- `@vitejs/plugin-react` → companion major compatible with the new Vite runtime
- Transitive: ensure bundled `esbuild` aligns with Vite’s release notes; override via `devDependencies` only if Vite does not surface the safety fixes we need.

## Pre-flight checklist
- Confirm Node.js toolchain meets the new baseline (expect Node 20.11+ per RFC discussions).
- Capture current baselines: `npm run build`, `npm run test:unit`, `npm run test:contracts`, `npm run preview -- --host`.
- Snapshot bundle metrics via `npm run build -- --mode production` + `dist/manifest.json` for comparison.
- Review upstream release notes for breaking config changes (HMR, SSR, JSX runtime flags).
- Verify third-party plugins: `@tanstack/react-query`, Tailwind, MSW, and pact helpers remain compatible.

## Upgrade steps
1. Create `chore/vite-vitest-major` branch and toggle CI to run on pushes.
2. Bump packages:
   - `npm install --save-dev vite@latest` (or `@next` if GA not tagged yet).
   - `npm install --save-dev vitest@latest @vitejs/plugin-react@latest jsdom@latest @types/node@latest`.
   - Add/upgrade `@vitest/ui` if we want the new reporting dashboard.
3. Review config changes:
   - `vite.config.ts`: adjust plugin options (e.g., new React fast-refresh hooks, `server.preTransformRequests`).
   - `vitest.config.ts`: adopt new defaults (`poolOptions`, `snapshot.serializers`) and ensure project-level overrides still work.
   - Update `tsconfig.json` paths if Vite enforces `moduleResolution` changes.
4. Regenerate lockfile (`npm install`) and re-run `npm audit --production` for awareness.
5. Validate dev server: `npm run dev` smoke test with dashboard pages.
6. Update docs if CLI commands or env vars change (e.g., new `VITE_` prefixes).

## Test sweep
- `npm run lint`
- `npm run typecheck`
- `npm run test:unit`
- `npm run test:contracts`
- `npm run build`
- `npm run preview -- --host 127.0.0.1 --port 4173`
- Browser spot-check (options dashboard, rules summary, PSD states).
- Regenerate Pact files (`tests/contracts/**/*.pact`) and diff for structural changes.

## Observability & metrics
- Compare bundle size and build duration (use `time npm run build` + measure `dist/assets/*` gzipped sizes).
- Track Vitest run time before/after; note any flaky tests.
- Ensure CI artifacts (pacts, coverage) remain stable.

## Rollback plan
- Keep pre-upgrade lockfile copy (`package-lock.json.pre-vite-major`).
- If regressions appear, revert dependency bumps and config diffs as a single commit.
- Coordinate with backend contract providers before publishing new Pact files.

## Open questions
- Do we need to pin `esbuild` explicitly for Apple Silicon signed binaries?
- Will Tailwind JIT require config tweaks under the new Vite pipeline?
- Any appetite for enabling Vitest’s browser runner once GA lands?

_Status: Ready for execution once the upstream GA lands._
