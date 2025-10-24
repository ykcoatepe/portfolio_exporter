import { useMemo, useState } from "react";
import clsx from "clsx";
import { Area, AreaChart, ResponsiveContainer, Tooltip, type TooltipProps } from "recharts";

import { useMsbHistory } from "../hooks/useMsbHistory";
import type { MsbReading } from "../lib/types";

const VIEWS = ["7D", "1Y"] as const;

type ViewOption = (typeof VIEWS)[number];

const ratioValue = (entry: MsbReading): number | null => {
  if (entry.term_ratio !== null && entry.term_ratio !== undefined) {
    return entry.term_ratio;
  }
  if (entry.vx2 === 0) {
    return null;
  }
  const computed = entry.vx1 / entry.vx2;
  return Number.isFinite(computed) ? computed : null;
};

const toSeries = (history: MsbReading[], limit: number) => {
  const trimmed = history.slice(0, limit).reverse();
  return trimmed.map((item) => ({
    date: item.date,
    hy: item.hy,
    ratio: ratioValue(item) ?? Number.NaN,
  }));
};

const formatHyTooltip: TooltipProps<number, string>["formatter"] = (value) => {
  const numeric = typeof value === "number" ? value : Number(value);
  return [Number.isFinite(numeric) ? numeric.toFixed(2) : "n/a", ""];
};

const formatRatioTooltip: TooltipProps<number, string>["formatter"] = (value) => {
  const numeric = typeof value === "number" ? value : Number(value);
  return [Number.isFinite(numeric) ? numeric.toFixed(3) : "n/a", ""];
};

export default function MSBMiniCharts(): JSX.Element {
  const [view, setView] = useState<ViewOption>("7D");
  const { data, isLoading, error } = useMsbHistory({ days: 365 });
  const limit = view === "7D" ? 7 : 365;
  const series = useMemo(() => toSeries(data ?? [], limit), [data, limit]);
  const hasData = series.length > 0;

  return (
    <section
      role="region"
      aria-label="MSB Mini Charts"
      className="rounded-3xl border border-slate-800/70 bg-slate-950/60 p-5 shadow-md"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
          MSB Signals
        </h2>
        <div className="inline-flex rounded-full border border-slate-700 bg-slate-900/60 p-1 text-sm">
          {VIEWS.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setView(option)}
              aria-pressed={view === option}
              className={clsx(
                "px-3 py-1 font-semibold uppercase tracking-wide transition",
                view === option
                  ? "rounded-full bg-slate-800 text-slate-100"
                  : "rounded-full text-slate-400 hover:text-slate-100",
              )}
            >
              {option}
            </button>
          ))}
        </div>
      </div>
      {isLoading ? <p className="mt-4 text-sm text-slate-400">Loading history…</p> : null}
      {error ? (
        <p className="mt-4 text-sm text-rose-300" role="alert">
          {error.message}
        </p>
      ) : null}
      {!hasData && !isLoading && !error ? (
        <p className="mt-4 text-sm text-slate-400">No MSB history available.</p>
      ) : null}
      {hasData ? (
        <div className="mt-6 grid gap-6 md:grid-cols-2">
          <figure role="img" aria-label="HY-OAS sparkline" className="rounded-2xl bg-slate-900/40 p-4">
            <figcaption className="text-xs font-semibold uppercase tracking-wide text-slate-400">
              HY-OAS
            </figcaption>
            <div className="mt-2 h-32">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={series} margin={{ top: 10, left: 0, right: 0, bottom: 0 }}>
                  <Tooltip<number, string>
                    contentStyle={{ backgroundColor: "#0f172a", border: "1px solid #1e293b" }}
                    labelFormatter={(label) => label as string}
                    formatter={formatHyTooltip}
                  />
                  <Area type="monotone" dataKey="hy" stroke="#34d399" fill="#34d39933" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </figure>
          <figure role="img" aria-label="VX1 over VX2 ratio sparkline" className="rounded-2xl bg-slate-900/40 p-4">
            <figcaption className="text-xs font-semibold uppercase tracking-wide text-slate-400">
              VX1/VX2 Ratio
            </figcaption>
            <div className="mt-2 h-32">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={series} margin={{ top: 10, left: 0, right: 0, bottom: 0 }}>
                  <Tooltip<number, string>
                    contentStyle={{ backgroundColor: "#0f172a", border: "1px solid #1e293b" }}
                    labelFormatter={(label) => label as string}
                    formatter={formatRatioTooltip}
                  />
                  <Area type="monotone" dataKey="ratio" stroke="#60a5fa" fill="#60a5fa33" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </figure>
        </div>
      ) : null}
    </section>
  );
}
