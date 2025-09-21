# 1. User Stories & Jobs
- As an equities PM, I need the dashboard to surface my single-stock P&L, exposure, and breaches so I can respond before market close.
- As an options strategist, I need combo-level visibility with summed Greeks and P&L to judge risk quickly.
- As an analyst on-call outside RTH, I need to know which marks were used (MID/LAST/PREV) and how stale they are before acting.
- As a risk manager, I need breach counters and a prioritized list so I know where to escalate immediately.
- As a trader, I need to filter and sort by symbol, expiry, and delta to locate positions for adjustments with the keyboard.
- As a compliance reviewer, I need read-only fundamentals (market cap, PE, earnings date) alongside breaches to validate narratives.
- As an operations engineer, I need confidence that all data came from existing feeds or see explicit gaps that new scripts must fill.
- As a QA lead, I need deterministic P&L and combo math with documented formulas for validation.
- As a product owner, I need telemetry to know when data staleness or combo detection quality regresses.

# 2. Information Architecture
- Page layout: Global filters header → Three vertical sections (Single Stocks, Option Combos & Legs, Rules & Fundamentals) with keyboard focus ring.
- Global quick filters: text symbol search (focusable shortcut `/`), account selector, mark source toggle (auto/manual), staleness threshold slider (default 5m).
- Section 1: Single Stocks table (sticky header) → row expand drawer with fundamentals + breaches timeline.
- Section 2: Option Combos summary table → expandable rows revealing legs table; nested quick filters (strategy type chips, expiry range slider) and secondary Single Legs table below combos.
- Section 3: Rules & Fundamentals panel → left column counters, right column breach list + fundamentals mini-grid.
- Sorting defaults: Single Stocks by descending Day P&L; Option Combos by abs(Exposure) then Day P&L; Single Legs by expiry ascending; breaches by severity desc then updated_at desc.
- Keyboard behavior: `Tab` cycles sections, `↑↓` move rows, `Space` expands, `Enter` toggles detail focus.

# 3. Section Specs
## 3.1 Single Stocks
- Columns: Symbol, Quantity (shares), Cost Basis ($), Mark Price ($ with mark pill), Day P&L ($/%), Total P&L ($/%), Exposure ($), Staleness (mm:ss).
- Units: Currency USD default; support multi-currency by suffix (EUR etc.). Quantities positive long, negative short.
- Default sort: Day P&L descending.
- Row expansion: shows Fundamentals mini-card (Market Cap, PE, Beta, Next Earnings) and Recent Breaches list (severity badge, rule name, triggered_at).
- Quick filters: sector dropdown, unrealized P&L range slider.

## 3.2 Option Combos
- Grouping: Prefer `combo_id` from IB Flex `StrategyId`; fallback to derived hash (see §6) using legs of same underlying/account/expiry pattern.
- Columns: Strategy Name (detected or from feed), Underlying, DTE, Net Credit/Debit, ΣDelta, ΣGamma, ΣTheta, ΣVega, Day P&L ($), Total P&L ($), Max Exposure ($), Mark Source pill, Staleness.
- Expand behavior: reveals legs table with columns (Leg# order, Right (Call/Put), Quantity, Strike, Expiry, Mark, Multiplier, Delta, Theta, Day P&L, Total P&L). Provide combo notes (detector rationale, missing data warnings).
- Sorting: default by descending abs(ΣDelta), secondary Day P&L.

## 3.3 Single Option Legs
- Table columns: Underlying, Expiry, Strike, Right, Quantity, Mark, Mark Source pill, Day P&L, Total P&L, Δ/Γ/Θ/ν, IV (if available), Staleness.
- Filters: Underlying multi-select, Expiry window (today, 7d, 30d, custom), Delta range slider, Only orphan legs toggle (not part of combo).

## 3.4 Rules & Fundamentals (MVP)
- Counters: Total active rules, Critical breaches (badge red), Warning breaches (badge amber), Resolved today (badge neutral).
- Top-5 breach list item: severity badge, rule name, affected symbol(s), triggered_at (relative), link icon to open detail (read-only).
- Fundamentals mini-tiles (per selected symbol or watchlist): Market Cap, Price/Earnings, Next Earnings Date, Dividend Yield (if available), each with source tooltip.

# 4. States & Behavior
- Market states: RTH (regular trading hours), ETH (extended), CLOSED. Mark selection logic: default MID; if missing -> LAST; if >5m stale -> PREV. Display pill `mark: MID` etc with reason tooltip ("IB Flex marks missing → using LAST").
- Staleness thresholds: highlight amber at >5m, red at >15m; display `stale 9m` text.
- Loading: skeleton rows per table, spinner fallback with `Esc` to cancel fetch.
- Empty: show guidance text ("No qualifying positions"), with shortcut to reset filters.
- Error: banner with retry button; surface underlying feed missing message (CSV path, timestamp).
- Tooltips: on mark pill, exposures, ΣGreeks definitions, breach severity scale.

# 5. Data Contracts (JSON Schemas)
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "Instrument",
  "type": "object",
  "required": ["symbol", "asset_type"],
  "properties": {
    "symbol": {"type": "string"},
    "asset_type": {"type": "string", "enum": ["EQUITY", "OPTION"]},
    "currency": {"type": "string", "minLength": 3, "maxLength": 3},
    "exchange": {"type": "string"}
  }
}
```
```json
{
  "$id": "Position",
  "type": "object",
  "required": ["instrument", "quantity", "cost_basis", "multiplier"],
  "properties": {
    "instrument": {"$ref": "Instrument"},
    "quantity": {"type": "number"},
    "cost_basis": {"type": "number"},
    "multiplier": {"type": "number"},
    "account": {"type": "string"},
    "open_date": {"type": "string", "format": "date"}
  }
}
```
```json
{
  "$id": "Quote",
  "type": "object",
  "required": ["symbol", "mark", "mark_source", "timestamp"],
  "properties": {
    "symbol": {"type": "string"},
    "mark": {"type": "number"},
    "bid": {"type": "number"},
    "ask": {"type": "number"},
    "mark_source": {"type": "string", "enum": ["MID", "LAST", "PREV"]},
    "timestamp": {"type": "string", "format": "date-time"}
  }
}
```
```json
{
  "$id": "Greeks",
  "type": "object",
  "required": ["delta", "gamma", "theta", "vega"],
  "properties": {
    "delta": {"type": "number"},
    "gamma": {"type": "number"},
    "theta": {"type": "number"},
    "vega": {"type": "number"}
  }
}
```
```json
{
  "$id": "ComboLeg",
  "type": "object",
  "required": ["leg_id", "position", "ratio"],
  "properties": {
    "leg_id": {"type": "string"},
    "position": {"$ref": "Position"},
    "ratio": {"type": "number"},
    "greeks": {"$ref": "Greeks"},
    "quote": {"$ref": "Quote"}
  }
}
```
```json
{
  "$id": "Combo",
  "type": "object",
  "required": ["combo_id", "strategy", "legs"],
  "properties": {
    "combo_id": {"type": "string"},
    "strategy": {"type": "string"},
    "underlying": {"type": "string"},
    "legs": {
      "type": "array",
      "items": {"$ref": "ComboLeg"},
      "minItems": 2
    },
    "net_price": {"type": "number"},
    "greeks": {"$ref": "Greeks"}
  }
}
```
```json
{
  "$id": "Rule",
  "type": "object",
  "required": ["rule_id", "name", "severity"],
  "properties": {
    "rule_id": {"type": "string"},
    "name": {"type": "string"},
    "severity": {"type": "string", "enum": ["INFO", "WARNING", "CRITICAL"]},
    "description": {"type": "string"}
  }
}
```
```json
{
  "$id": "Breach",
  "type": "object",
  "required": ["breach_id", "rule_id", "symbol", "triggered_at", "status"],
  "properties": {
    "breach_id": {"type": "string"},
    "rule_id": {"type": "string"},
    "symbol": {"type": "string"},
    "triggered_at": {"type": "string", "format": "date-time"},
    "status": {"type": "string", "enum": ["OPEN", "ACKNOWLEDGED", "RESOLVED"]},
    "notes": {"type": "string"}
  }
}
```
```json
{
  "$id": "Fundamental",
  "type": "object",
  "required": ["symbol", "market_cap", "pe_ratio"],
  "properties": {
    "symbol": {"type": "string"},
    "market_cap": {"type": "number"},
    "pe_ratio": {"type": "number"},
    "beta": {"type": "number"},
    "next_earnings": {"type": "string", "format": "date"},
    "dividend_yield": {"type": "number"}
  }
}
```

# 6. Combo Detection Rules
- Vertical spreads: same underlying, same expiry, two legs, opposite rights, strikes sorted; combo_id hash = `hash(account|underlying|expiry|min_strike|max_strike|vertical)`.
- Calendars: same underlying, same strike, different expiry within 90 days; rights identical; require opposite quantity signs; combo_id includes expiries sorted.
- Straddles/Strangles: same expiry, both call+put at same strike (straddle) or adjacent strikes (strangle) with equal absolute quantity.
- Iron Condor/Butterfly: four legs, two calls + two puts, expiries equal; wings symmetric (strike offsets match). Validate credit/debit sign. Hash includes inner/outer strikes.
- Ratios: legs sharing underlying+expiry where absolute quantity ratios not equal 1; tag as ratio with normalized fraction.
- When IB provides partial IDs, extend hash: `sha1("PSD" + account + join(sorted(leg_signature)))` where leg_signature=`{right}:{strike}:{expiry}:{ratio}`.

# 7. P&L & Greeks Math
- Equity Day P&L = `(mark - prior_close) * quantity * multiplier` (multiplier default 1); Total P&L = `(mark - cost_basis) * quantity * multiplier`.
- Option leg Day P&L = `(mark - prior_mark) * quantity * multiplier`; Total P&L = `(mark - average_entry) * quantity * multiplier`.
- Combo P&L = sum of leg P&L; combo net credit/debit = `∑(entry_price * quantity * multiplier)`; Greeks aggregated by leg-weighted sum (e.g., combo_delta = `∑(leg_delta * quantity * multiplier)`).
- Exposure = `mark * quantity * multiplier` for equities; for options use underlying spot * delta * quantity * multiplier.

# 8. Performance & Telemetry
- Target: p95 render ≤200 ms for payload with 500 legs and 150 equities; pre-process combos server-side.
- Server metrics: positions_count, equities_count, option_legs_count, combos_matched, combo_detection_ms, quote_refresh_ms, stale_quotes_count, breach_count.
- Client metrics: hydration_ms, filter_latency_ms, rows_rendered, focus_trap_events, error_rate.
- Alert when stale_quotes_count > 10 or combo_detection_ms > 100 ms.

# 9. Test Plan (Given/When/Then)
- Given two call legs same expiry opposite quantities, When detector runs, Then vertical combo is created with hash matching §6.
- Given only LAST price available, When mark selection runs, Then mark pill shows `LAST` with tooltip reason and P&L uses LAST.
- Given option legs with mismatched expiries, When combo detection executes, Then legs remain in Single Legs table flagged as orphans.
- Given equity with multiplier 1 and mark drift +1.50, When Day P&L computes for 200 shares, Then result is 300.00.
- Given combo legs with stale timestamps (>15m), When dashboard renders, Then staleness column turns red and telemetry logs stale_quotes_count.
- Given rules feed with three critical, two warning breaches, When counters render, Then totals display 5 with critical=3 warning=2.
- Given ambiguous roll (two verticals share legs), When detection runs, Then system picks IB combo_id if present else marks conflict warning in notes.

# 10. Incremental Delivery Plan
- Milestone 1: Data ingestion layer reusing IB Flex + existing CSVs; acceptance: Position, Quote, Fundamental schemas validated, unit tests for loaders.
- Milestone 2: Single Stocks table with expansion + staleness logic; acceptance: keyboard navigation, mark pill fallbacks, unit tests for P&L math.
- Milestone 3: Combo detection + Option Combos view; acceptance: detectors cover vertical/calendar/iron condor, telemetry combos_matched emitted, expandable legs table.
- Milestone 4: Single Option Legs view with orphan filtering and delta/expiry filters; acceptance: filter shortcuts work, orphan toggle verified.
- Milestone 5: Rules & Fundamentals panel + telemetry wiring; acceptance: counters accurate, breach list sorted, fundamentals tiles show sourced data, metrics logged.
- Milestone 6: Test automation + performance harness; acceptance: GWT scenarios automated in pytest, load test confirms p95 ≤200 ms, memory digest updated.
