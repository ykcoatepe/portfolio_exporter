import clsx from "clsx";

import type { MarkSource } from "../lib/types";

const markSourceTone: Record<MarkSource, string> = {
  MID: "bg-sky-500/10 text-sky-300 border border-sky-500/30",
  LAST: "bg-amber-500/10 text-amber-300 border border-amber-500/40",
  PREV: "bg-slate-500/10 text-slate-200 border border-slate-500/40",
};

export function MarkBadge({ source }: { source: MarkSource }) {
  return (
    <span
      className={clsx(
        "inline-flex min-w-[2.75rem] items-center justify-center rounded-full px-2 py-0.5 text-xs font-medium uppercase tracking-wide",
        markSourceTone[source],
      )}
      title={`Mark source: ${source}`}
    >
      {source}
    </span>
  );
}
