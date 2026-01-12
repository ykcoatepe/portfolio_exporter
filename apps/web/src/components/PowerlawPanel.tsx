import clsx from "clsx";
import { useState } from "react";

import { formatPercent } from "../lib/format";
import { resolveApiBaseUrl } from "../lib/http";
import type { PowerlawSnapshot } from "../lib/types";

export async function triggerPowerlawRefresh(): Promise<void> {
  const origin = resolveApiBaseUrl();
  const response = await fetch(`${origin}/powerlaw/refresh`, {
    method: "POST",
    headers: { Accept: "application/json" },
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(`Powerlaw refresh failed (${response.status})`);
  }
}

const formatNumber = (value: number | null | undefined, digits = 2): string => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "N/A";
  }
  return value.toFixed(digits);
};

const formatPercentMaybe = (value: number | null | undefined): string =>
  formatPercent(value ?? null, {
    alreadyScaled: true,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

const formatDate = (value: string | null | undefined): string => {
  if (!value) {
    return "N/A";
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return value;
  }
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) {
    return value;
  }
  return new Date(parsed).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
};

const formatBoolean = (value: boolean | null | undefined): string => {
  if (value === null || value === undefined) {
    return "N/A";
  }
  return value ? "YES" : "NO";
};

type MetricCardProps = {
  label: string;
  value: string;
  detail?: string | null;
};

const MetricCard = ({ label, value, detail }: MetricCardProps) => (
  <div className="rounded-2xl border border-slate-900/60 bg-slate-950/40 p-4">
    <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
    <div className="mt-2 text-2xl font-semibold text-slate-100">{value}</div>
    {detail ? <div className="mt-1 text-xs text-slate-500">{detail}</div> : null}
  </div>
);

type PowerlawPanelProps = {
  powerlaw?: PowerlawSnapshot | null;
  onRefresh?: () => Promise<unknown>;
};

export default function PowerlawPanel({ powerlaw, onRefresh }: PowerlawPanelProps): JSX.Element {
  const [refreshing, setRefreshing] = useState(false);

  if (!powerlaw) {
    return (
      <section className="rounded-3xl border border-slate-900/60 bg-slate-950/50 p-5">
        <h2 className="text-xl font-semibold text-slate-100">Powerlaw Signals</h2>
        <p className="mt-3 text-sm text-slate-400">
          Powerlaw signals are not available. Check that PSD_POWERLAW_REPO is configured.
        </p>
      </section>
    );
  }
  const stale = powerlaw.stale === true;
  const refreshStatus = powerlaw.refresh?.status ?? "idle";
  const refreshError = powerlaw.refresh?.last_error ?? null;
  const asOfLabel = formatDate(powerlaw.as_of ?? undefined);
  const dataQuality = powerlaw.data_quality ?? "N/A";
  const vixLabel = formatNumber(powerlaw.vix_spot);
  const vvixLabel = formatNumber(powerlaw.vvix_spot);
  const staleReason = powerlaw.stale_reason ?? "behind_trading_day";
  const backwardationLabel =
    powerlaw.vx_backwardation === null || powerlaw.vx_backwardation === undefined
      ? "Backwardation: N/A"
      : powerlaw.vx_backwardation
        ? "Backwardation: YES"
        : "Backwardation: NO";

  const staleMessage = stale
    ? refreshStatus === "running"
      ? "Refreshing Powerlaw data now..."
      : refreshStatus === "timeout"
        ? `Refresh timed out${refreshError ? ` (${refreshError})` : ""} - showing last snapshot.`
        : refreshStatus === "failed"
          ? `Refresh failed${refreshError ? ` (${refreshError})` : ""} - showing last snapshot.`
          : staleReason === "missing_snapshot"
            ? "No Powerlaw snapshot found yet."
            : staleReason === "config_missing"
              ? "Powerlaw feed not configured. Set PSD_POWERLAW_REPO."
              : "Snapshot is behind the latest trading day."
    : null;
  const canRefresh = stale && staleReason !== "config_missing";
  const refreshDisabled = refreshing || refreshStatus === "running";

  const handleRefresh = async () => {
    if (!canRefresh || refreshDisabled) {
      return;
    }
    setRefreshing(true);
    try {
      await triggerPowerlawRefresh();
      await onRefresh?.();
    } catch {
      await onRefresh?.();
    } finally {
      setRefreshing(false);
    }
  };

  const equityRows = Object.entries(powerlaw.equity_weights ?? {}).sort((a, b) =>
    a[0].localeCompare(b[0]),
  );
  const hedgeRows = Object.entries(powerlaw.hedge_notional ?? {}).sort((a, b) =>
    a[0].localeCompare(b[0]),
  );

  return (
    <section className="rounded-3xl border border-slate-900/60 bg-slate-950/50 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-slate-100">Powerlaw Signals</h2>
          <p className="mt-1 text-sm text-slate-400">As of {asOfLabel}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={clsx(
              "rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide",
              stale
                ? "border-amber-400/40 bg-amber-500/10 text-amber-200"
                : "border-emerald-400/40 bg-emerald-500/10 text-emerald-200",
            )}
          >
            {stale ? "STALE" : "LIVE"}
          </span>
          <span className="rounded-full border border-slate-800/70 bg-slate-900/60 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-slate-300">
            DATA: {dataQuality}
          </span>
        </div>
      </div>

      {staleMessage ? (
        <div className="mt-3 rounded-2xl border border-amber-400/40 bg-amber-500/10 px-4 py-2 text-sm text-amber-200">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span>{staleMessage}</span>
            {canRefresh ? (
              <button
                type="button"
                onClick={handleRefresh}
                disabled={refreshDisabled}
                className={clsx(
                  "rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wide",
                  refreshDisabled
                    ? "border-slate-700 text-slate-500"
                    : "border-amber-400/50 text-amber-100 hover:border-amber-300 hover:text-amber-50",
                )}
              >
                {refreshDisabled ? "Refreshing..." : "Refresh Powerlaw"}
              </button>
            ) : null}
          </div>
          {refreshStatus === "running" ? (
            <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-slate-900/60">
              <div className="h-full w-1/2 animate-pulse rounded-full bg-amber-300/70" />
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="grid gap-3 sm:grid-cols-2">
          <MetricCard
            label="PLKE"
            value={formatNumber(powerlaw.plke)}
            detail={powerlaw.plke_band_alpha ? `Band: ${powerlaw.plke_band_alpha}` : null}
          />
          <MetricCard
            label="Risk State"
            value={powerlaw.risk_state ?? "N/A"}
            detail={powerlaw.vol_bucket ? `Vol bucket: ${powerlaw.vol_bucket}` : null}
          />
          <MetricCard
            label="V/VIX Util"
            value={formatPercentMaybe(powerlaw.vutil_used)}
            detail={powerlaw.vutil_source ? `Source: ${powerlaw.vutil_source}` : null}
          />
          <MetricCard
            label="VIX / VVIX"
            value={`${vixLabel} / ${vvixLabel}`}
            detail={backwardationLabel}
          />
          <MetricCard
            label="Small-cap Theta"
            value={formatPercentMaybe(powerlaw.small_cap?.theta_pct_nav)}
            detail={powerlaw.small_cap?.plke_band ? `Band: ${powerlaw.small_cap?.plke_band}` : null}
          />
          <MetricCard
            label="Small-cap Gate"
            value={formatBoolean(powerlaw.small_cap?.can_open_new_trades)}
            detail="Can open new trades"
          />
        </div>

        <div className="space-y-3">
          <div className="rounded-2xl border border-slate-900/60 bg-slate-950/40 p-4">
            <div className="text-xs uppercase tracking-wide text-slate-500">Equity Weights</div>
            {equityRows.length ? (
              <div className="mt-2 space-y-1 text-sm text-slate-200">
                {equityRows.map(([symbol, weight]) => (
                  <div key={symbol} className="flex items-center justify-between">
                    <span className="font-medium">{symbol}</span>
                    <span className="font-mono text-slate-300">{formatPercentMaybe(weight)}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="mt-2 text-sm text-slate-500">N/A</div>
            )}
          </div>

          <div className="rounded-2xl border border-slate-900/60 bg-slate-950/40 p-4">
            <div className="text-xs uppercase tracking-wide text-slate-500">Hedge Notional</div>
            {hedgeRows.length ? (
              <div className="mt-2 space-y-1 text-sm text-slate-200">
                {hedgeRows.map(([name, weight]) => (
                  <div key={name} className="flex items-center justify-between">
                    <span className="font-medium">{name}</span>
                    <span className="font-mono text-slate-300">{formatPercentMaybe(weight)}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="mt-2 text-sm text-slate-500">N/A</div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
