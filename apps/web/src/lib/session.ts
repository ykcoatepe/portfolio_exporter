import type { MarketSession, MarketSessionApiResponse, MarketSessionState } from "./types";

const DEFAULT_EXCHANGE = "XNYS";
const DEFAULT_TZ = "America/New_York";
const VALID_STATES: ReadonlySet<MarketSessionState> = new Set(["RTH", "ETH", "CLOSED"]);

function coalesceString(value?: string | null): string | null {
  if (typeof value === "string" && value.length > 0) {
    return value;
  }
  return null;
}

export function normalizeSession(
  payload: MarketSessionApiResponse | null | undefined,
): MarketSession | null {
  if (!payload || typeof payload !== "object") {
    return null;
  }

  const stateRaw = typeof payload.state === "string" ? payload.state : String(payload.state ?? "");
  const state = stateRaw.toUpperCase() as MarketSessionState;
  if (!VALID_STATES.has(state)) {
    return null;
  }

  const exchange = coalesceString(payload.exchange) ?? DEFAULT_EXCHANGE;
  const tz = coalesceString(payload.tz) ?? DEFAULT_TZ;

  const asOf =
    coalesceString(payload.as_of) ??
    coalesceString(payload.asOf) ??
    new Date().toISOString();

  const rthOpen = coalesceString(payload.rth_open) ?? coalesceString(payload.rthOpen);
  const rthClose = coalesceString(payload.rth_close) ?? coalesceString(payload.rthClose);
  const source = coalesceString(payload.source) ?? "fallback";
  const note = coalesceString(payload.note);

  return {
    exchange,
    tz,
    state,
    asOf,
    rthOpen: rthOpen ?? null,
    rthClose: rthClose ?? null,
    source,
    note,
  };
}
