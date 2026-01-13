import clsx from "clsx";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { MSB_CURRENT_QUERY_KEY, MSB_STATUS_QUERY_KEY, triggerMsbRefresh } from "../lib/msb";

const EXPORT_CSV_PATH = "/msb/history.csv?days=365";
const EXPORT_PARQUET_PATH = "/msb/history.parquet?days=365";

export default function MSBActionBox(): JSX.Element {
  const queryClient = useQueryClient();
  const [refreshing, setRefreshing] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);

  const handleRefresh = async () => {
    if (refreshing) {
      return;
    }
    setRefreshing(true);
    setRefreshError(null);
    try {
      const result = await triggerMsbRefresh();
      if (!result.ok || result.status !== "updated") {
        const detail = result.detail ? ` (${result.detail})` : "";
        setRefreshError(`Refresh ${result.status}${detail}`.trim());
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "MSB refresh failed";
      setRefreshError(message);
    } finally {
      await queryClient.invalidateQueries({ queryKey: MSB_CURRENT_QUERY_KEY });
      await queryClient.invalidateQueries({ queryKey: ["msb.history"] });
      await queryClient.invalidateQueries({ queryKey: MSB_STATUS_QUERY_KEY });
      setRefreshing(false);
    }
  };

  return (
    <section
      role="region"
      aria-label="MSB Hedge Actions"
      className="rounded-3xl border border-slate-800/70 bg-slate-950/60 p-5 shadow-md"
    >
      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
        Hedge Playbook
      </h2>
      <p className="mt-3 text-base text-slate-200">
        Default hedge: <strong>VIX 25/35 call spread</strong> (2–4 weeks to expiry, target cost
        <span className="whitespace-nowrap"> 0.10–0.35%</span> of NAV).
      </p>
      <p className="mt-2 text-sm text-slate-300">
        Already hedged? Maintain size; roll on breach or when ΔMSB ≥ 10.
      </p>
      <div className="mt-4 flex flex-wrap gap-3">
        <button
          type="button"
          onClick={handleRefresh}
          disabled={refreshing}
          className={clsx(
            "inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-semibold uppercase tracking-wide transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950",
            refreshing
              ? "border-slate-700 text-slate-500"
              : "border-sky-400/70 text-sky-100 hover:border-sky-300 hover:text-sky-50",
          )}
        >
          {refreshing ? "Refreshing MSB..." : "Refresh MSB"}
        </button>
        <a
          href={EXPORT_CSV_PATH}
          download
          className="inline-flex items-center gap-2 rounded-full bg-sky-500/90 px-4 py-2 text-sm font-semibold uppercase tracking-wide text-slate-950 transition hover:bg-sky-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
        >
          Export MSB (CSV)
        </a>
        <a
          href={EXPORT_PARQUET_PATH}
          download
          className="inline-flex items-center gap-2 rounded-full bg-sky-500/20 px-4 py-2 text-sm font-semibold uppercase tracking-wide text-slate-200 transition hover:bg-sky-400/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
        >
          Export MSB (Parquet)
        </a>
      </div>
      {refreshError ? (
        <p className="mt-2 text-xs text-rose-300">MSB refresh failed. {refreshError}</p>
      ) : null}
      <p className="mt-2 text-xs text-slate-400">
        CSV suits spreadsheets; Parquet keeps schema fidelity for notebooks and pipelines.
      </p>
    </section>
  );
}
