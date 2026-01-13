import { useMemo, useState } from "react";
import clsx from "clsx";
import {
  Area,
  AreaChart,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  type TooltipProps,
} from "recharts";

import { useMsbHistory } from "../hooks/useMsbHistory";
import { useMsbSignalsHelp } from "../hooks/useMsbSignalsHelp";
import type { MsbReading } from "../lib/types";

const VIEWS = ["7D", "1Y"] as const;

type ViewOption = (typeof VIEWS)[number];

type SeriesPoint = {
  date: string;
  hy: number;
  ratio: number;
};

type SeriesStats = {
  last: number | null;
  prev: number | null;
  delta: number | null;
  min: number | null;
  max: number | null;
};

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

const toSeries = (history: MsbReading[], limit: number): SeriesPoint[] => {
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

const isFiniteNumber = (value: number | null | undefined): value is number =>
  typeof value === "number" && Number.isFinite(value);

const calcStats = (values: number[]): SeriesStats => {
  if (!values.length) {
    return { last: null, prev: null, delta: null, min: null, max: null };
  }
  const sorted = [...values].sort((a, b) => a - b);
  const last = values[values.length - 1] ?? null;
  const prev = values.length > 1 ? values[values.length - 2] ?? null : null;
  const delta =
    last !== null && prev !== null ? Number((last - prev).toFixed(4)) : null;
  return {
    last,
    prev,
    delta,
    min: sorted[0] ?? null,
    max: sorted[sorted.length - 1] ?? null,
  };
};

const formatValue = (value: number | null, digits: number) =>
  value === null || !Number.isFinite(value) ? "—" : value.toFixed(digits);

const formatDelta = (delta: number | null, digits: number) => {
  if (delta === null || !Number.isFinite(delta)) {
    return "—";
  }
  const sign = delta > 0 ? "+" : "";
  return `${sign}${delta.toFixed(digits)}`;
};

export default function MSBMiniCharts(): JSX.Element {
  const [view, setView] = useState<ViewOption>("7D");
  const { data, isLoading, error } = useMsbHistory({ days: 365 });
  const { data: help, isLoading: helpLoading, error: helpError } = useMsbSignalsHelp();
  const limit = view === "7D" ? 7 : 365;
  const series = useMemo(() => toSeries(data ?? [], limit), [data, limit]);
  const hyValues = useMemo(() => series.map((item) => item.hy).filter(isFiniteNumber), [series]);
  const ratioValues = useMemo(
    () => series.map((item) => item.ratio).filter(isFiniteNumber),
    [series],
  );
  const hyStats = useMemo(() => calcStats(hyValues), [hyValues]);
  const ratioStats = useMemo(() => calcStats(ratioValues), [ratioValues]);
  const hasData = series.length > 0;

  return (
    <section
      role="region"
      aria-label="MSB Mini Charts"
      className="rounded-3xl border border-slate-800/70 bg-slate-950/60 p-5 shadow-md"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
            MSB Signals
          </h2>
          <div className="relative group">
            <button
              type="button"
              aria-label="MSB signals help"
              className="flex h-5 w-5 items-center justify-center rounded-full border border-slate-700 text-[11px] font-semibold text-slate-300 transition hover:border-slate-500 hover:text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400/60"
            >
              i
            </button>
            <div
              role="tooltip"
              className={clsx(
                "absolute left-0 top-7 z-20 w-[320px] max-w-[80vw] rounded-2xl border border-slate-800/70 bg-slate-950/95 p-4 text-xs text-slate-200 opacity-0 shadow-xl transition",
                "pointer-events-none group-hover:opacity-100 group-focus-within:opacity-100",
              )}
            >
              {helpLoading ? (
                <p className="text-slate-400">Loading explanation...</p>
              ) : helpError ? (
                <p className="text-rose-300">Help unavailable.</p>
              ) : help ? (
                <div className="space-y-3">
                  <div>
                    <div className="text-sm font-semibold text-slate-100">{help.title}</div>
                    {help.subtitle ? (
                      <div className="mt-1 text-[11px] text-slate-400">{help.subtitle}</div>
                    ) : null}
                  </div>
                  {help.sections.map((section) => (
                    <div key={section.title} className="space-y-1">
                      <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-300">
                        {section.title}
                      </div>
                      <ul className="list-disc space-y-1 pl-4 text-slate-200">
                        {section.bullets.map((item, idx) => (
                          <li key={`${section.title}-${idx}`}>{item}</li>
                        ))}
                      </ul>
                    </div>
                  ))}
                  {help.footnotes?.length ? (
                    <div className="space-y-1 border-t border-slate-800/70 pt-2 text-[11px] text-slate-400">
                      {help.footnotes.map((note, idx) => (
                        <div key={`footnote-${idx}`}>{note}</div>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          </div>
        </div>
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
            <div className="flex items-start justify-between gap-3">
              <figcaption className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                HY-OAS
              </figcaption>
              <div className="text-right">
                <div className="text-sm font-semibold text-emerald-200">
                  {formatValue(hyStats.last, 2)}
                </div>
                <div className="text-[11px] text-slate-400">
                  1D {formatDelta(hyStats.delta, 2)} • Range {formatValue(hyStats.min, 2)}–
                  {formatValue(hyStats.max, 2)}
                </div>
              </div>
            </div>
            <div className="mt-2 h-32">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={series} margin={{ top: 10, left: 0, right: 0, bottom: 0 }}>
                  <Tooltip<number, string>
                    contentStyle={{ backgroundColor: "#0f172a", border: "1px solid #1e293b" }}
                    labelFormatter={(label) => label as string}
                    formatter={formatHyTooltip}
                  />
                  {hyStats.last !== null ? (
                    <ReferenceDot
                      x={series[series.length - 1]?.date}
                      y={hyStats.last}
                      r={3}
                      fill="#34d399"
                      stroke="#0f172a"
                      strokeWidth={1.5}
                    />
                  ) : null}
                  <Area type="monotone" dataKey="hy" stroke="#34d399" fill="#34d39933" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </figure>
          <figure role="img" aria-label="VX1 over VX2 ratio sparkline" className="rounded-2xl bg-slate-900/40 p-4">
            <div className="flex items-start justify-between gap-3">
              <figcaption className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                VX1/VX2 Ratio
              </figcaption>
              <div className="text-right">
                <div className="text-sm font-semibold text-sky-200">
                  {formatValue(ratioStats.last, 3)}
                </div>
                <div className="text-[11px] text-slate-400">
                  1D {formatDelta(ratioStats.delta, 3)} • Range {formatValue(ratioStats.min, 3)}–
                  {formatValue(ratioStats.max, 3)}
                </div>
              </div>
            </div>
            <div className="mt-2 h-32">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={series} margin={{ top: 10, left: 0, right: 0, bottom: 0 }}>
                  <Tooltip<number, string>
                    contentStyle={{ backgroundColor: "#0f172a", border: "1px solid #1e293b" }}
                    labelFormatter={(label) => label as string}
                    formatter={formatRatioTooltip}
                  />
                  {ratioStats.last !== null ? (
                    <ReferenceDot
                      x={series[series.length - 1]?.date}
                      y={ratioStats.last}
                      r={3}
                      fill="#60a5fa"
                      stroke="#0f172a"
                      strokeWidth={1.5}
                    />
                  ) : null}
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
