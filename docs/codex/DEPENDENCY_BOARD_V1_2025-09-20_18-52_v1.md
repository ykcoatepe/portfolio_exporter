# Dependency Tracking Board

_Last updated: 2025-09-20 · Owner: deps guild_

## Deprecations to monitor

| Package (version) | Source chain | Deprecated message | Planned resolution |
| --- | --- | --- | --- |
| `glob@8.1.0` | `@pact-foundation/pact` → `@pact-foundation/pact-core` → `pino-pretty` → `help-me` → `glob` | "Glob versions prior to v9 are no longer supported" | Expect removal once the Pact stack updates to `glob@9+` (track upcoming Pact major). Re-run `npm ls glob` after bump. |
| `inflight@1.0.6` | `@pact-foundation/pact` → `@pact-foundation/pact-core` → `pino-pretty` → `help-me` → `glob` → `inflight` | "This module is not supported, and leaks memory…" | Should disappear automatically when `glob` moves to v9 (drops `inflight`). Verify during Pact major trial. |

## Follow-up actions
- Re-check after upgrading `@pact-foundation/pact` major and rerun `npm ls glob` / `npm ls inflight`.
- If the deps persist, raise an issue upstream (pino/helme) or consider patching via overrides.
