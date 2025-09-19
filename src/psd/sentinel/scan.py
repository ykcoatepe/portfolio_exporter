from __future__ import annotations

import asyncio
import importlib
import logging
import os
import time
from collections.abc import Callable, Iterable

from psd.core.store import append_event, init, latest_snapshot, tail_events

log = logging.getLogger("psd.scan")
RULES_FN_SPEC = os.getenv("PSD_RULES_FN", "").strip()  # e.g. "portfolio_exporter.psd_rules:evaluate"


def _load_rules(spec: str) -> Callable[[dict], Iterable[str]]:
    if not spec:
        return lambda risk: []  # default: no rules
    if ":" not in spec:
        raise ValueError("Expected 'module:function' in PSD_RULES_FN")
    mod_name, fn_name = spec.split(":", 1)
    fn = getattr(importlib.import_module(mod_name), fn_name)
    if not callable(fn):
        raise TypeError(f"{spec} is not callable")
    return fn


EVALUATE_RULES = _load_rules(RULES_FN_SPEC)


async def run() -> None:
    init()
    last_id = 0
    while True:
        events = tail_events(last_id=last_id, limit=200)
        if not events:
            await asyncio.sleep(0.5)
            continue
        last_id = events[-1][0]
        # re-scan on any snapshot/diff
        if any(kind in ("snapshot", "diff") for _, kind, _ in events):
            snap = latest_snapshot()
            if not snap:
                continue
            risk = snap.get("risk", {})
            try:
                breaches: list[str] = list(EVALUATE_RULES(risk))
            except Exception as e:
                log.warning("rules evaluation failed: %s", e, exc_info=False)
                breaches = []
            if breaches:
                append_event("breach", {"ts": time.time(), "breaches": breaches, "risk": risk})


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
