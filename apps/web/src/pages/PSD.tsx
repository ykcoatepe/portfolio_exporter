import CombosTable from "../components/CombosTable";
import OptionLegsTable from "../components/OptionLegsTable";
import RulesPanel from "../components/RulesPanel";
import StocksTable from "../components/StocksTable";

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
        className="space-y-6 rounded-3xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/70 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
      >
        <CombosTable />
        <OptionLegsTable />
      </section>

      <section
        id="section-rules"
        aria-label="Rules and Fundamentals"
        tabIndex={0}
        className="rounded-3xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/70 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
      >
        <RulesPanel />
      </section>
    </main>
  </div>
);

export default PSDPage;
