import { useEffect, useMemo, useRef, useState } from "react";
import clsx from "clsx";

import {
  type RuleBreachSummary,
  type RuleCounters,
  type RuleSeverity,
  type SymbolFundamentals,
  useFundamentals,
  useRulesSummary,
} from "../hooks/useRules";
import {
  type RuleCatalogValidationResult,
  usePreviewRules,
  usePublishRules,
  useRuleCatalog,
  useReloadRules,
  useValidateRules,
} from "../hooks/useRuleCatalog";

const severityStyles: Record<RuleSeverity, string> = {
  CRITICAL:
    "border-rose-500/40 bg-rose-500/15 text-rose-200 focus-visible:ring-rose-400/60",
  WARNING:
    "border-amber-500/40 bg-amber-400/10 text-amber-100 focus-visible:ring-amber-400/60",
  INFO: "border-sky-500/40 bg-sky-400/10 text-sky-100 focus-visible:ring-sky-400/60",
};

const severityLabel: Record<RuleSeverity, string> = {
  CRITICAL: "Critical",
  WARNING: "Warning",
  INFO: "Info",
};

const relativeTimeFormat = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
const dateFormatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
});
const peFormatter = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1, minimumFractionDigits: 1 });

const formatRelativeTime = (iso: string): string => {
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) {
    return "—";
  }
  const diffMs = ts - Date.now();
  const diffSeconds = Math.round(diffMs / 1000);
  const absSeconds = Math.abs(diffSeconds);
  if (absSeconds < 60) {
    return relativeTimeFormat.format(diffSeconds, "second");
  }
  const diffMinutes = Math.round(diffSeconds / 60);
  if (Math.abs(diffMinutes) < 120) {
    return relativeTimeFormat.format(diffMinutes, "minute");
  }
  const diffHours = Math.round(diffMinutes / 60);
  if (Math.abs(diffHours) < 48) {
    return relativeTimeFormat.format(diffHours, "hour");
  }
  const diffDays = Math.round(diffHours / 24);
  return relativeTimeFormat.format(diffDays, "day");
};

const formatMarketCap = (value: number | null | undefined): string => {
  if (!value || !Number.isFinite(value)) {
    return "—";
  }
  const abs = Math.abs(value);
  const sign = value < 0 ? -1 : 1;
  if (abs >= 1_000_000_000_000) {
    return `${(sign * abs / 1_000_000_000_000).toFixed(1)}T`;
  }
  if (abs >= 1_000_000_000) {
    return `${(sign * abs / 1_000_000_000).toFixed(1)}B`;
  }
  if (abs >= 1_000_000) {
    return `${(sign * abs / 1_000_000).toFixed(1)}M`;
  }
  return value.toLocaleString("en-US");
};

const formatPe = (value: number | null | undefined): string => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return peFormatter.format(value);
};

const formatDividend = (value: number | null | undefined): string => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return `${(value * 100).toFixed(2)}%`;
};

const formatEarnings = (value: string | null | undefined): string => {
  if (!value) {
    return "—";
  }
  const ts = Date.parse(value);
  if (Number.isNaN(ts)) {
    return value;
  }
  return dateFormatter.format(new Date(ts));
};

const uniqueSymbolsFromBreaches = (top: RuleBreachSummary[]): string[] => {
  const symbols = new Set<string>();
  for (const breach of top) {
    if (breach.symbol) {
      symbols.add(breach.symbol.toUpperCase());
    }
  }
  return Array.from(symbols);
};

const countersOrder: RuleSeverity[] = ["CRITICAL", "WARNING", "INFO"];

export function RulesPanel(): JSX.Element {
  const {
    data: summary,
    isLoading,
    isFetching,
    isError,
    error,
    refetch,
  } = useRulesSummary();

  const catalogQuery = useRuleCatalog();
  const reloadMutation = useReloadRules();
  const validateMutation = useValidateRules();
  const previewMutation = usePreviewRules();
  const publishMutation = usePublishRules();

  const [isCatalogPanelOpen, setCatalogPanelOpen] = useState(false);
  const [catalogText, setCatalogText] = useState("");
  const [lastValidation, setLastValidation] = useState<RuleCatalogValidationResult | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [validationTimestamp, setValidationTimestamp] = useState<string | null>(null);

  const topBreaches = useMemo(() => (summary?.top ?? []).slice(0, 5), [summary?.top]);
  const focusSymbols = useMemo(() => {
    const fromSummary = Array.isArray(summary?.focus_symbols)
      ? summary?.focus_symbols.filter((symbol): symbol is string => typeof symbol === "string")
      : [];
    if (fromSummary.length > 0) {
      return fromSummary;
    }
    return uniqueSymbolsFromBreaches(summary?.top ?? []);
  }, [summary?.focus_symbols, summary?.top]);

  const fundamentals = useFundamentals(focusSymbols);
  const [activeIndex, setActiveIndex] = useState(0);
  const itemRefs = useRef<Array<HTMLLIElement | null>>([]);

  useEffect(() => {
    setActiveIndex(0);
  }, [topBreaches.length]);

  const focusItem = (index: number) => {
    const node = itemRefs.current[index];
    if (!node) {
      return;
    }
    if (typeof window !== "undefined" && typeof window.requestAnimationFrame === "function") {
      window.requestAnimationFrame(() => node.focus());
    } else {
      setTimeout(() => node.focus(), 0);
    }
  };

  const handleListKey = (event: React.KeyboardEvent<HTMLLIElement>, index: number) => {
    if (topBreaches.length === 0) {
      return;
    }
    const moveFocus = (nextIndex: number) => {
      const clamped = ((nextIndex % topBreaches.length) + topBreaches.length) % topBreaches.length;
      setActiveIndex(clamped);
      focusItem(clamped);
    };

    switch (event.key) {
      case "ArrowDown":
      case "j":
        event.preventDefault();
        moveFocus(index + 1);
        break;
      case "ArrowUp":
      case "k":
        event.preventDefault();
        moveFocus(index - 1);
        break;
      case "Home":
        event.preventDefault();
        moveFocus(0);
        break;
      case "End":
        event.preventDefault();
        moveFocus(topBreaches.length - 1);
        break;
      default:
        break;
    }
  };

  const renderFundamentalTile = (entry: SymbolFundamentals) => (
    <div
      key={entry.symbol}
      className="flex flex-col gap-2 rounded-xl border border-slate-900/80 bg-slate-950/40 p-4"
      role="group"
      aria-label={`Fundamentals for ${entry.symbol}`}
    >
      <div className="flex items-baseline justify-between">
        <span className="text-sm uppercase tracking-wide text-slate-400">
          {entry.symbol}
        </span>
        {entry.company ? (
          <span className="max-w-[12rem] truncate text-xs text-slate-500">
            {entry.company}
          </span>
        ) : null}
      </div>
      <dl className="grid grid-cols-2 gap-3 text-sm text-slate-200">
        <div>
          <dt className="text-xs uppercase tracking-wide text-slate-500">Market Cap</dt>
          <dd className="font-medium text-slate-100">{formatMarketCap(entry.market_cap ?? null)}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-slate-500">P/E</dt>
          <dd className="font-medium text-slate-100">{formatPe(entry.pe ?? null)}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-slate-500">Next Earnings</dt>
          <dd className="font-medium text-slate-100">
            {formatEarnings(entry.next_earnings ?? null)}
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-slate-500">Dividend Yield</dt>
          <dd className="font-medium text-slate-100">
            {formatDividend(entry.dividend_yield ?? null)}
          </dd>
        </div>
      </dl>
    </div>
  );

  const catalogData = catalogQuery.data ?? null;
  const catalogVersionLabel = catalogData ? `v${catalogData.version}` : "v0";
  const catalogUpdatedLabel = catalogData?.updatedAt ? formatRelativeTime(catalogData.updatedAt) : null;
  const catalogUpdatedBy = catalogData?.updatedBy ?? null;
  const catalogRulesCount = catalogData?.rulesCount ?? 0;
  const catalogRulesLabel = catalogData ? `${catalogRulesCount} rules` : "— rules";

  const isValidationPending = validateMutation.isPending || previewMutation.isPending;
  const isPublishPending = publishMutation.isPending;
  const validationTop = lastValidation?.top ?? [];
  const validationCounters = lastValidation?.counters ?? null;
  const validationDiff = lastValidation?.diff ?? null;
  const catalogErrorMessage =
    catalogQuery.isError && catalogQuery.error instanceof Error ? catalogQuery.error.message : null;
  const reloadErrorMessage =
    reloadMutation.isError && reloadMutation.error instanceof Error ? reloadMutation.error.message : null;

  const resetValidationState = () => {
    setLastValidation(null);
    setValidationError(null);
    setValidationTimestamp(null);
  };

  const handleCatalogPanelToggle = () => {
    setCatalogPanelOpen((current) => {
      const nextOpen = !current;
      if (!nextOpen) {
        resetValidationState();
      }
      return nextOpen;
    });
  };

  const handleValidateSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = catalogText.trim();
    if (!trimmed) {
      setValidationError("Catalog YAML is required before validation.");
      setLastValidation(null);
      return;
    }
    setValidationError(null);
    setLastValidation(null);
    setValidationTimestamp(null);
    try {
      const baseResult = await validateMutation.mutateAsync({ catalogText: trimmed });
      let result: RuleCatalogValidationResult = baseResult;
      if (baseResult.ok) {
        try {
          result = await previewMutation.mutateAsync({ catalogText: trimmed });
        } catch (previewError) {
          setValidationError((previewError as Error).message);
        }
      }
      setLastValidation(result);
      setValidationTimestamp(new Date().toISOString());
    } catch (err) {
      setValidationError((err as Error).message);
    }
  };

  const handlePublish = async () => {
    const trimmed = catalogText.trim();
    if (!trimmed) {
      setValidationError("Catalog YAML is required before publishing.");
      return;
    }
    if (!lastValidation?.ok) {
      setValidationError("Validate the catalog before publishing.");
      return;
    }
    setValidationError(null);
    try {
      await publishMutation.mutateAsync({ catalogText: trimmed });
      setCatalogPanelOpen(false);
      setCatalogText("");
      resetValidationState();
    } catch (err) {
      setValidationError((err as Error).message);
    }
  };

  const isInitialLoading = isLoading || (isFetching && !summary);

  if (isInitialLoading) {
    return (
      <section
        aria-label="Rules summary loading"
        className="rounded-3xl border border-slate-900/80 bg-slate-950/60 p-8 text-sm text-slate-400"
      >
        Loading rules summary…
      </section>
    );
  }

  if (isError) {
    return (
      <section
        aria-label="Rules summary error"
        className="rounded-3xl border border-rose-500/40 bg-rose-950/30 p-8"
      >
        <div className="flex flex-col gap-4 text-sm text-rose-100">
          <p>Unable to load rules summary.{" "}
            {error?.message ? <span className="text-rose-200/80">({error.message})</span> : null}
          </p>
          <button
            type="button"
            onClick={() => refetch()}
            className="inline-flex w-fit items-center gap-2 rounded-lg border border-rose-500/40 bg-rose-900/40 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-rose-100 transition hover:border-rose-400/60 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400/70 focus-visible:ring-offset-2 focus-visible:ring-offset-rose-950"
          >
            Retry
          </button>
        </div>
      </section>
    );
  }

  if (!summary) {
    return (
      <section
        aria-label="Rules summary"
        className="rounded-3xl border border-slate-900/80 bg-slate-950/60 p-8 text-sm text-slate-400"
      >
        No rule breaches to display right now.
      </section>
    );
  }

  return (
    <section
      aria-label="Rules summary"
      className="rounded-3xl border border-slate-900/80 bg-slate-950/60 shadow-inner shadow-slate-950/40"
    >
      <div className="flex flex-col gap-4 border-b border-slate-900/70 px-6 py-6 md:flex-row md:items-center md:justify-between">
        <div className="space-y-2">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Rules Catalog</p>
            <div className="mt-2 flex flex-wrap items-baseline gap-3 text-slate-100">
              <span className="text-2xl font-semibold text-slate-100">Rules {catalogVersionLabel}</span>
              {catalogUpdatedLabel ? (
                <span className="text-xs text-slate-400">Updated {catalogUpdatedLabel}</span>
              ) : (
                <span className="text-xs text-slate-500">Updated —</span>
              )}
              {catalogUpdatedBy ? (
                <span className="text-xs text-slate-500">by {catalogUpdatedBy}</span>
              ) : null}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
            <span>{catalogRulesLabel}</span>
            {catalogQuery.isFetching ? <span className="text-slate-400">Refreshing…</span> : null}
            {catalogErrorMessage ? <span className="text-rose-300">{catalogErrorMessage}</span> : null}
            {reloadErrorMessage ? <span className="text-rose-300">{reloadErrorMessage}</span> : null}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={() => reloadMutation.mutate()}
            disabled={reloadMutation.isPending}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-700/70 bg-slate-900/60 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-slate-200 transition hover:border-slate-500/70 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400/70 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {reloadMutation.isPending ? "Reloading…" : "Reload"}
          </button>
          <button
            type="button"
            onClick={handleCatalogPanelToggle}
            className="inline-flex items-center gap-2 rounded-lg border border-sky-500/40 bg-sky-500/10 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-sky-200 transition hover:border-sky-400/60 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400/70 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
          >
            {isCatalogPanelOpen ? "Hide Validator" : "Validate & Publish"}
          </button>
        </div>
      </div>
      {isCatalogPanelOpen ? (
        <div className="border-b border-slate-900/70 bg-slate-950/40 px-6 py-6">
          <form className="space-y-4" onSubmit={handleValidateSubmit}>
            <div className="space-y-2">
              <label htmlFor="rules-catalog-text" className="text-xs uppercase tracking-wide text-slate-400">
                Catalog YAML
              </label>
              <textarea
                id="rules-catalog-text"
                value={catalogText}
                onChange={(event) => {
                  setCatalogText(event.target.value);
                  if (validationError) {
                    setValidationError(null);
                  }
                }}
                rows={6}
                className="w-full rounded-lg border border-slate-800 bg-slate-950/80 px-3 py-2 text-sm text-slate-100 shadow-inner focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400/60"
                placeholder="Paste updated rules.yaml content here…"
              />
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="submit"
                disabled={isValidationPending}
                className="inline-flex items-center gap-2 rounded-lg border border-sky-500/40 bg-sky-500/10 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-sky-200 transition hover:border-sky-400/60 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400/70 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isValidationPending ? "Validating…" : "Validate"}
              </button>
              <button
                type="button"
                onClick={handlePublish}
                disabled={isPublishPending || !lastValidation?.ok}
                className="inline-flex items-center gap-2 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-emerald-200 transition hover:border-emerald-400/60 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/70 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isPublishPending ? "Publishing…" : "Publish"}
              </button>
              <button
                type="button"
                onClick={handleCatalogPanelToggle}
                className="inline-flex items-center gap-2 rounded-lg border border-slate-800 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-slate-300 transition hover:border-slate-600 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400/70 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
              >
                Close
              </button>
            </div>
            {validationError ? <p className="text-sm text-rose-300">{validationError}</p> : null}
            {lastValidation ? (
              <div className="space-y-4 rounded-2xl border border-slate-900/70 bg-slate-950/50 p-4">
                <div className="flex flex-wrap items-center gap-3">
                  <span
                    className={clsx(
                      "text-sm font-semibold",
                      lastValidation.ok ? "text-emerald-300" : "text-rose-300",
                    )}
                  >
                    {lastValidation.ok ? "Validation passed" : "Validation failed"}
                  </span>
                  {validationTimestamp ? (
                    <span className="text-xs text-slate-500">as of {formatRelativeTime(validationTimestamp)}</span>
                  ) : null}
                </div>
                {validationCounters ? (
                  <div className="flex flex-wrap gap-4 text-xs text-slate-300">
                    <span>
                      Critical: <span className="font-semibold text-rose-200">{validationCounters.critical}</span>
                    </span>
                    <span>
                      Warning: <span className="font-semibold text-amber-200">{validationCounters.warning}</span>
                    </span>
                    <span>
                      Info: <span className="font-semibold text-sky-200">{validationCounters.info}</span>
                    </span>
                    <span>
                      Total: <span className="font-semibold text-slate-200">{validationCounters.total}</span>
                    </span>
                  </div>
                ) : null}
                {validationDiff && (validationDiff.added.length || validationDiff.changed.length || validationDiff.removed.length) ? (
                  <div className="space-y-2 text-xs text-slate-400">
                    <p className="font-semibold text-slate-300">Catalog diff</p>
                    <div className="flex flex-wrap gap-4">
                      <span>Added {validationDiff.added.length}</span>
                      <span>Changed {validationDiff.changed.length}</span>
                      <span>Removed {validationDiff.removed.length}</span>
                    </div>
                  </div>
                ) : null}
                {validationTop.length > 0 ? (
                  <div className="space-y-2">
                    <p className="text-xs uppercase tracking-wide text-slate-400">Top Breaches Preview</p>
                    <ul className="space-y-2">
                      {validationTop.map((entry) => (
                        <li
                          key={entry.id}
                          className="rounded-lg border border-slate-800 bg-slate-900/60 px-3 py-2 text-sm text-slate-200"
                        >
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <span className="font-semibold text-slate-100">{entry.rule}</span>
                            <span className="text-xs uppercase tracking-wide text-slate-400">
                              {severityLabel[entry.severity]}
                            </span>
                          </div>
                          <p className="text-xs text-slate-400">{entry.subject}</p>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {lastValidation.errors.length ? (
                  <div className="space-y-1 text-sm text-rose-200">
                    {lastValidation.errors.map((message, index) => (
                      <p key={index}>{message}</p>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
          </form>
        </div>
      ) : null}
      <div className="flex flex-col gap-8 border-b border-slate-900/70 px-6 py-8 md:flex-row md:items-start md:justify-between">
        <div className="md:max-w-xs">
          <header className="space-y-4">
            <div>
              <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Rules</p>
              <p className="mt-2 text-4xl font-semibold text-slate-100">
                {summary.breaches.total}
              </p>
            </div>
            <dl className="space-y-3">
              {countersOrder.map((level) => {
                const counterKey = level.toLowerCase() as keyof RuleCounters;
                return (
                  <div key={level} className="flex items-center justify-between">
                    <dt className="text-sm text-slate-400">{severityLabel[level]}</dt>
                    <dd className="text-sm font-medium text-slate-100">
                      {summary.breaches[counterKey]}
                    </dd>
                  </div>
                );
              })}
            </dl>
          </header>
          <p className="mt-6 text-xs text-slate-500">
            Updated {formatRelativeTime(summary.as_of)}
          </p>
        </div>

        <div className="flex-1">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">
              Top Breaches
            </h2>
            {isFetching ? (
              <span className="text-xs text-slate-500">Refreshing…</span>
            ) : null}
          </div>
          {topBreaches.length === 0 ? (
            <p className="mt-4 text-sm text-slate-500">No active breaches detected.</p>
          ) : (
            <ul role="list" aria-label="Top rule breaches" className="mt-4 space-y-3">
              {topBreaches.map((breach, index) => (
                <li
                  key={breach.id}
                  ref={(node) => {
                    itemRefs.current[index] = node;
                  }}
                  role="listitem"
                  aria-label={`${severityLabel[breach.severity]} breach: ${breach.rule}`}
                  tabIndex={activeIndex === index ? 0 : -1}
                  onFocus={() => setActiveIndex(index)}
                  onKeyDown={(event) => handleListKey(event, index)}
                  className={clsx(
                    "flex items-start justify-between gap-4 rounded-2xl border px-4 py-3 text-sm transition focus-visible:outline-none focus-visible:ring-2",
                    severityStyles[breach.severity],
                  )}
                >
                  <div className="flex flex-1 items-start gap-4">
                    <span className="mt-0.5 inline-flex h-8 min-w-[4.5rem] items-center justify-center rounded-full border border-current px-2 text-xs font-semibold uppercase tracking-wide">
                      {severityLabel[breach.severity]}
                    </span>
                    <div className="space-y-1">
                      <p className="text-sm font-semibold text-slate-100">{breach.rule}</p>
                      <p className="text-sm text-slate-300">
                        {breach.subject}
                        {breach.symbol ? (
                          <span className="ml-2 rounded-full bg-slate-900/60 px-2 py-0.5 text-xs uppercase tracking-wide text-slate-400">
                            {breach.symbol}
                          </span>
                        ) : null}
                      </p>
                      <p className="text-xs text-slate-400">
                        {formatRelativeTime(breach.occurred_at)}
                      </p>
                    </div>
                  </div>
                  <button
                    type="button"
                    className="mt-0.5 inline-flex items-center rounded-lg border border-slate-700/70 bg-slate-900/70 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-sky-200 transition hover:border-sky-400/50 hover:text-sky-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400/70 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
                    aria-label={`Open detail for ${breach.rule}`}
                  >
                    Open Detail
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="px-6 py-6">
        <header className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-300">
            Fundamentals Snapshot
          </h2>
          {fundamentals.isFetching ? (
            <span className="text-xs text-slate-500">Loading…</span>
          ) : null}
        </header>
        {fundamentals.isError ? (
          <p className="mt-4 text-sm text-rose-200">
            Unable to load fundamentals ({fundamentals.error?.message ?? "unexpected error"}).
          </p>
        ) : null}
        {!fundamentals.isError && (fundamentals.data?.length ?? 0) === 0 ? (
          <p className="mt-4 text-sm text-slate-500">
            Select a rule breach with an associated symbol to see fundamentals.
          </p>
        ) : null}
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {fundamentals.data?.map((entry) => renderFundamentalTile(entry))}
        </div>
      </div>
    </section>
  );
}

export default RulesPanel;
