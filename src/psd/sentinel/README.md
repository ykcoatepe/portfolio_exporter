# PSD Sentinel

## Scan Loop
- `psd.sentinel.scan.run()` tails the ledger with `psd.core.store.tail_events`, reacts to every `snapshot`/`diff`, and replays the most recent snapshot to evaluate rules.
- Rules are injected via `PSD_RULES_FN="module:function"`; the callable receives the `risk` block of the snapshot and yields string IDs for breached policies.
- The engine in `psd.sentinel.engine` enriches the snapshot with combos, VaR, and breaker context before rules fire, so downstream alerts always carry the same payload shape.

## Pacing
- The scan loop blocks on ledger reads and sleeps for 0.5 s when idle, keeping CPU usage low while still reacting quickly to fresh ticks.
- `psd.ingestor` controls event cadence; tuning `PSD_HEARTBEAT_S` adjusts how often the store is checkpointed and how frequently Sentinel receives re-scan triggers.
- Quieting and snooze behaviour is memoized on disk (`var/memos/psd_memos.jsonl`) and replayed on startup so alert suppression persists across restarts.

## Alert Bus
- When rules return non-empty breaches, `append_event("breach", {...})` publishes them to the ledger, allowing the SPA and any automation hooks listening to `/stream` to react immediately.
- Alert DTOs include the risk snapshot, breaker state, and memo metadata; memo writes happen via `psd.sentinel.memos.write_jsonl` for auditability.
- Downstream processors should treat breach events as level-triggered—Sentinel emits them once per breach per quiet window and relies on memos to suppress duplicates.
