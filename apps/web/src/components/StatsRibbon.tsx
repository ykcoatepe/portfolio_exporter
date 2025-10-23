import { useMemo } from "react";
import clsx from "clsx";

import { usePortfolioMetrics } from "../hooks/usePortfolioMetrics";
import { useSession } from "../hooks/useSession";
import { useStats } from "../hooks/useStats";
import { formatDuration, formatMoney, formatPercent } from "../lib/format";
import { formatSigned, stalenessTone, valueTone } from "./tableUtils";

const relativeTimeFormat = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

const STALE_THRESHOLD_SECONDS = 300;

function toFinite(value: number | null | undefined): number | null {
  if (value === null || value === undefined) {
    return null;
  }
  const asNumber = Number(value);
  return Number.isFinite(asNumber) ? asNumber : null;
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

export default function StatsRibbon(): JSX.Element {
  const { data: stats } = useStats();
  const metrics = usePortfolioMetrics();
  const sessionSeed = stats?.session ?? stats?.sessionInfo ?? null;
  const sessionResult = useSession(sessionSeed);
  const session = sessionSeed ?? sessionResult.data ?? null;

  const now = Date.now();

  const updatedTimestamp = useMemo(() => {
    const preferred = parseIsoToMs(stats?.latestTs);
    if (preferred !== null) {
      return preferred;
    }

    const candidates: number[] = [];
    const sessionTimestamp = parseIsoToMs(stats?.session?.asOf ?? stats?.sessionInfo?.asOf);
    if (sessionTimestamp !== null) {
      candidates.push(sessionTimestamp);
    }
    const normalizedMetricsTimestamp = normalizeEpochMs(metrics.updatedAt);
    if (normalizedMetricsTimestamp !== null) {
      candidates.push(normalizedMetricsTimestamp);
    }
    const statsUpdatedTimestamp = parseIsoToMs(stats?.updatedAt);
    if (statsUpdatedTimestamp !== null) {
      candidates.push(statsUpdatedTimestamp);
    }
    return selectLatestTimestamp(candidates);
  }, [
    metrics.updatedAt,
    stats?.latestTs,
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

  const stalenessSeconds = metrics.stalenessSeconds;
  const isStale = stalenessSeconds !== null && stalenessSeconds >= STALE_THRESHOLD_SECONDS;
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

  const dataSourceLabel = stats?.dataSource ?? "—";

  const cards = [
    {
      key: "day-pnl",
      label: "Day P&L",
      value: formatMoney(metrics.dayPnl),
      tone: valueTone(metrics.dayPnl),
    },
    {
      key: "unrealized-pnl",
      label: "Unrealized P&L",
      value: formatMoney(metrics.totalPnl),
      tone: valueTone(metrics.totalPnl),
    },
    {
      key: "sum-delta",
      label: "ΣΔ",
      value: formatSigned(metrics.sumDelta, 2),
      tone: valueTone(metrics.sumDelta),
    },
    {
      key: "sum-theta",
      label: "ΣΘ / day",
      value: formatSigned(metrics.sumTheta, 2),
      tone: valueTone(metrics.sumTheta),
    },
    {
      key: "net-liq",
      label: "Net Liq",
      value: formatMoney(toFinite(stats?.netLiq)),
      tone: valueTone(toFinite(stats?.netLiq)),
    },
    {
      key: "var-95",
      label: "VaR 95%",
      value: formatMoney(toFinite(stats?.var95)),
      tone: valueTone(toFinite(stats?.var95)),
    },
    {
      key: "margin",
      label: "Margin %",
      value: formatPercent(toFinite(stats?.marginPct), { alreadyScaled: true }),
      tone: valueTone(toFinite(stats?.marginPct)),
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
          {isStale && stalenessLabel ? (
            <span
              className={clsx(
                "rounded-full border px-2.5 py-1 text-xs font-medium uppercase tracking-wide",
                stalenessClassName,
                "border-current bg-slate-900/60",
              )}
              title={`Stale for ${stalenessLabel}`}
            >
              stale {stalenessLabel}
            </span>
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
              className={clsx("mt-1 font-mono text-lg", card.tone)}
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
