const EXPORT_PATH = "/msb/history.csv?days=365";

export default function MSBActionBox(): JSX.Element {
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
        <a
          href={EXPORT_PATH}
          download
          className="inline-flex items-center gap-2 rounded-full bg-sky-500/90 px-4 py-2 text-sm font-semibold uppercase tracking-wide text-slate-950 transition hover:bg-sky-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
        >
          Export MSB (CSV)
        </a>
        <p className="text-xs text-slate-400">
          CSV includes the latest 365 readings for downstream analysis.
        </p>
      </div>
    </section>
  );
}
