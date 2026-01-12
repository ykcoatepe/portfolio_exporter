import { useMemo } from "react";
import clsx from "clsx";

import { usePortfolioMetrics } from "../hooks/usePortfolioMetrics";
import { useSession } from "../hooks/useSession";
import { useStats } from "../hooks/useStats";
import { formatDuration, formatMoney, formatPercent } from "../lib/format";
import { formatSigned, stalenessTone, valueTone } from "./tableUtils";

const relativeTimeFormat = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

const FALLBACK_STALE_THRESHOLD_SEC = 300;

function toFinite(value: number | null | undefined): number | null {
  if (value === null || value === undefined) {
    return null;
  }
  const asNumber = Number(value);
  return Number.isFinite(asNumber) ? asNumber : null;
}

function pickFirstNumber(
  ...values: Array<number | null | undefined>
): number | null {
  for (const value of values) {
    const normalized = toFinite(value);
    if (normalized !== null) {
      return normalized;
    }
  }
  return null;
}

function maxNumber(
  ...values: Array<number | null | undefined>
): number | null {
  const normalized = values
    .map((value) => toFinite(value))
    .filter((value): value is number => value !== null);
  if (normalized.length === 0) {
    return null;
  }
  return Math.max(...normalized);
}

function selectLatestTimestamp(timestamps: number[]): number | null {
  if (timestamps.length === 0) {
    return null;
  }
  return Math.max(...timestamps);
}

function normalizeEpochMs(value: number | null | undefined): number | null {
  if (value === null || value === undefined) {
    return null;
  }
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return null;
  }
  return numeric < 1e12 ? Math.trunc(numeric * 1000) : Math.trunc(numeric);
}

function parseIsoToMs(value: string | null | undefined): number | null {
  if (!value) {
    return null;
  }
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
}

function formatRelativeFromNow(timestamp: number, now: number): string {
  const diffMs = timestamp - now;
  const diffSeconds = Math.round(diffMs / 1000);
  const absSeconds = Math.abs(diffSeconds);

  if (absSeconds < 60) {
    return relativeTimeFormat.format(diffSeconds, "second");
  }
  if (absSeconds < 3600) {
    return relativeTimeFormat.format(Math.round(diffSeconds / 60), "minute");
  }
  if (absSeconds < 86_400) {
    return relativeTimeFormat.format(Math.round(diffSeconds / 3600), "hour");
  }
  return relativeTimeFormat.format(Math.round(diffSeconds / 86_400), "day");
}

type StatsRibbonProps = {
  onRefresh?: () => void;
  refreshing?: boolean;
  refreshStatus?: "idle" | "running" | "success" | "failed" | "timeout";
};

export default function StatsRibbon({ onRefresh, refreshing, refreshStatus }: StatsRibbonProps): JSX.Element {
  const { data: stats } = useStats();
  const metrics = usePortfolioMetrics();
  const sessionSeed = stats?.session ?? stats?.sessionInfo ?? null;
  const sessionResult = useSession(sessionSeed);
  const session = sessionSeed ?? sessionResult.data ?? null;

  const now = Date.now();

  const updatedTimestamp = useMemo(() => {
    const candidates: number[] = [];
    const statsUpdated = parseIsoToMs(stats?.updatedAt);
    if (statsUpdated !== null) {
      candidates.push(statsUpdated);
    }
    const statsSessionTimestamp = parseIsoToMs(
      stats?.session?.asOf ?? stats?.sessionInfo?.asOf,
    );
    if (statsSessionTimestamp !== null) {
      candidates.push(statsSessionTimestamp);
    }
    const resolvedSessionTimestamp = parseIsoToMs(session?.asOf);
    if (resolvedSessionTimestamp !== null) {
      candidates.push(resolvedSessionTimestamp);
    }
    const normalizedMetricsTimestamp = normalizeEpochMs(metrics.updatedAt);
    if (normalizedMetricsTimestamp !== null) {
      candidates.push(normalizedMetricsTimestamp);
    }
    return selectLatestTimestamp(candidates);
  }, [
    metrics.updatedAt,
    session?.asOf,
    stats?.session?.asOf,
    stats?.sessionInfo?.asOf,
    stats?.updatedAt,
  ]);

  const updatedLabel = updatedTimestamp
    ? formatRelativeFromNow(updatedTimestamp, now)
    : "—";
  const updatedTitle = updatedTimestamp
    ? new Date(updatedTimestamp).toLocaleString()
    : undefined;

  const totals = stats?.totals ?? null;
  const stalenessSeconds = maxNumber(
    metrics.stalenessSeconds,
    stats?.stalenessSec,
    totals?.stalenessSecs,
  );
  const isStale =
    stalenessSeconds !== null && stalenessSeconds >= FALLBACK_STALE_THRESHOLD_SEC;
  const stalenessLabel = stalenessSeconds !== null ? formatDuration(stalenessSeconds) : null;
  const stalenessClassName = stalenessTone(stalenessSeconds);

  const sessionLabel = session?.state ?? "—";
  const sessionUpdatedTimestamp = session?.asOf ? Date.parse(session.asOf) : NaN;
  const hasSessionTimestamp = Number.isFinite(sessionUpdatedTimestamp);
  const sessionUpdatedLabel = hasSessionTimestamp
    ? formatRelativeFromNow(sessionUpdatedTimestamp, now)
    : "—";
  const sessionUpdatedTitle = hasSessionTimestamp
    ? new Date(sessionUpdatedTimestamp).toLocaleString()
    : undefined;

  const dayPnlValue = pickFirstNumber(
    metrics.dayPnl,
    totals?.pnlDay,
    stats?.dayPnl,
  );
  const unrealizedValue = pickFirstNumber(
    metrics.totalPnl,
    totals?.unrealized,
    stats?.unrealizedPnl,
  );
  const sigmaTotalValue = pickFirstNumber(
    metrics.sumDelta,
    totals?.sumDelta,
    stats?.sigmaTotal,
  );
  const sigmaPerDayValue = pickFirstNumber(
    metrics.sumTheta,
    totals?.sumTheta,
    stats?.sigmaPerDay,
  );
  const netLiqValue = stats?.netLiq;
  const var95Value = stats?.var95;
  const marginValue = stats?.marginPct;
  const dataSourceLabel = stats?.dataSource ?? "—";

  const cards = [
    {
      key: "day-pnl",
      label: "Day P&L",
      value: formatMoney(dayPnlValue),
      tone: valueTone(dayPnlValue),
    },
    {
      key: "unrealized-pnl",
      label: "Unrealized P&L",
      value: formatMoney(unrealizedValue),
      tone: valueTone(unrealizedValue),
    },
    {
      key: "sum-delta",
      label: "ΣΔ",
      value: formatSigned(sigmaTotalValue, 2),
      tone: valueTone(sigmaTotalValue),
    },
    {
      key: "sum-theta",
      label: "ΣΘ / day",
      value: formatSigned(sigmaPerDayValue, 2),
      tone: valueTone(sigmaPerDayValue),
    },
    {
      key: "net-liq",
      label: "Net Liq",
      value: formatMoney(toFinite(netLiqValue)),
      tone: valueTone(toFinite(netLiqValue)),
    },
    {
      key: "var-95",
      label: "VaR 95%",
      value: formatMoney(toFinite(var95Value)),
      tone: valueTone(toFinite(var95Value)),
    },
    {
      key: "margin",
      label: "Margin %",
      value: formatPercent(toFinite(marginValue), { alreadyScaled: true }),
      tone: valueTone(toFinite(marginValue)),
    },
    {
      key: "updated",
      label: "Updated",
      value: updatedLabel,
      tone: "text-slate-300",
      title: updatedTitle,
    },
  ];

  return (
    <section
      role="region"
      aria-label="Portfolio stats"
      tabIndex={0}
      className="rounded-3xl border border-slate-800/70 bg-slate-900/60 p-5 shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/70 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
          Portfolio Stats
        </h2>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex flex-col items-end text-right">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-300">
              SESSION: {sessionLabel}
            </span>
            <span
              className="text-[11px] uppercase tracking-wide text-slate-500"
              title={sessionUpdatedTitle}
            >
              updated {sessionUpdatedLabel}
            </span>
          </div>
          <span
            data-testid="data-source-chip"
            className="rounded-full border border-slate-800/70 bg-slate-900/60 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-slate-300"
          >
            DATA • {dataSourceLabel}
          </span>
          {isStale ? (
            <span
              data-testid="stale-chip"
              className={clsx(
                "rounded-full border px-2.5 py-1 text-xs font-medium uppercase tracking-wide",
                stalenessClassName,
                "border-current bg-slate-900/60",
              )}
              title={stalenessLabel ? `Stale for ${stalenessLabel}` : undefined}
            >
              STALE {stalenessLabel ?? "—"}
            </span>
          ) : null}
          {onRefresh ? (
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onRefresh}
                disabled={refreshing || refreshStatus === "running"}
                className={clsx(
                  "rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wide",
                  refreshing || refreshStatus === "running"
                    ? "border-slate-700 text-slate-500"
                    : "border-sky-400/50 text-sky-100 hover:border-sky-300 hover:text-sky-50",
                )}
              >
                {refreshing || refreshStatus === "running" ? "Refreshing..." : "Refresh PSD"}
              </button>
              {refreshStatus === "running" ? (
                <div className="h-1.5 w-24 overflow-hidden rounded-full bg-slate-800">
                  <div className="h-full w-1/2 animate-pulse rounded-full bg-sky-400/70" />
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6 xl:grid-cols-8">
        {cards.map((card) => (
          <dl
            key={card.key}
            className="rounded-2xl border border-slate-800/60 bg-slate-950/40 p-3"
          >
            <dt className="text-xs uppercase tracking-wide text-slate-400">{card.label}</dt>
            <dd
              data-testid="stat-value"
              className={clsx(
                "mt-1 font-mono text-lg",
                card.tone,
                isStale ? "opacity-70" : undefined,
              )}
              title={card.title}
            >
              {card.value}
            </dd>
          </dl>
        ))}
      </div>
    </section>
  );
}
