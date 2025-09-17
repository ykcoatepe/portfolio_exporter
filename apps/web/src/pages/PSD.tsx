import StocksTable from "../components/StocksTable";

const PlaceholderCard = ({
  title,
  description,
  bullets,
}: {
  title: string;
  description: string;
  bullets: string[];
}) => (
  <div className="rounded-2xl border border-dashed border-slate-800/70 bg-slate-950/40 p-6 shadow-inner shadow-slate-950/30">
    <h3 className="text-base font-semibold text-slate-100">{title}</h3>
    <p className="mt-3 max-w-2xl text-sm text-slate-400">{description}</p>
    <ul className="mt-4 list-disc space-y-2 pl-6 text-sm text-slate-400">
      {bullets.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  </div>
);

const PSDPage = () => (
  <div className="min-h-screen bg-slate-950 text-slate-100">
    <header className="border-b border-slate-900/70 bg-slate-950/80">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Portfolio Sentinel Dashboard</h1>
          <p className="mt-1 text-sm text-slate-400">
            Keyboard-first monitoring for equities and derivatives portfolios.
          </p>
        </div>
        <div className="rounded-full border border-slate-800 bg-slate-900/80 px-4 py-2 text-xs uppercase tracking-wide text-slate-400">
          PSD • Preview
        </div>
      </div>
    </header>

    <main className="mx-auto flex max-w-6xl flex-col gap-10 px-6 py-8" aria-label="Portfolio Sentinel sections">
      <section
        id="section-stocks"
        aria-label="Single Stocks"
        tabIndex={0}
        className="rounded-3xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/70 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
      >
        <StocksTable />
      </section>

      <section
        id="section-options"
        aria-label="Options Combos and Legs"
        tabIndex={0}
        className="rounded-3xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/70 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
      >
        <PlaceholderCard
          title="Options Combos & Legs"
          description="Upcoming: combo grouping, leg drill-down, and streaming Greeks with the same keyboard affordances as equities."
          bullets={[
            "Strategy filters (verticals, calendars, ratio spreads)",
            "Nested legs table with mark-source badges",
            "Delta, gamma, theta, vega aggregates with alerts",
          ]}
        />
      </section>

      <section
        id="section-rules"
        aria-label="Rules and Fundamentals"
        tabIndex={0}
        className="rounded-3xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/70 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
      >
        <PlaceholderCard
          title="Rules & Fundamentals"
          description="Placeholder for breach counters, alert timelines, and fundamentals mini-tiles once the services land."
          bullets={[
            "Critical and warning breach badges with relative timestamps",
            "Top rule breaches prioritized for escalation",
            "Fundamentals mini-grid (market cap, PE, earnings, dividend)",
          ]}
        />
      </section>
    </main>
  </div>
);

export default PSDPage;
