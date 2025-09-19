from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any

from ..core.alerts import emit_alerts
from ..core.fs_utils import find_latest_chain_for_symbol
from ..core.ib_export import export_ib_basket, export_ib_notes
from ..core.market_clock import TZ_TR, premarket_window_tr, pretty_tr, rth_window_tr
from ..core.micro_momo import (
    entry_trigger,
    passes_filters,
    score_components,
    size_and_targets,
    tier_and_dir,
)
from ..core.micro_momo_optionpicker import pick_structure
from ..core.micro_momo_sources import (
    enrich_inplace,
    find_chain_file_for_symbol,
    load_chain_csv,
    load_scan_csv,
)
from ..core.micro_momo_types import ResultRow, ScanRow, Structure
from ..core.symbols import load_alias_map, normalize_symbols

DEFAULT_CFG: dict[str, Any] = {
    "filters": {
        "price_bounds": {"min": 5.0, "max": 500.0},
        "float_max_millions": 2000.0,
        "adv_usd_min_millions": 5.0,
        "premkt_gap_min_pct": 0.0,
        "rvol_min": 1.0,
        "near_money_oi_min": 50,
        "opt_spread_max_pct": 0.05,
        "halts_max": 0,
    },
    "options": {"min_width": 5.0, "max_spread_pct": 0.25},
    "liquidity": {"min_oi": 50},
    "sizing": {"risk_budget": 250.0, "max_contracts": 5},
    "targets": {"tp_pct": 0.5, "sl_pct": 0.5},
    "tiers": {"A_tier": 75.0, "B_tier": 55.0},
    "weights": {
        "gap": 1.0,
        "rvol": 1.0,
        "float": 0.8,
        "short": 0.5,
        "liquidity": 1.0,
        "options_quality": 1.0,
        "vwap": 1.0,
        "pattern": 0.8,
        "news_buzz": 0.6,
    },
    "rvol_confirm_entry": 1.5,
    "data": {
        "mode": "enrich",
        "providers": ["ib", "yahoo"],
        "offline": False,
        "halts_source": "nasdaq",
        "cache": {"enabled": True, "dir": "out/.cache", "ttl_sec": 60},
    },
}


def _direction_from_structure(template: str, fallback: str) -> str:
    t = (template or "").lower()
    if t == "bearcallcredit":
        return "short"
    if t in ("debitcall", "bullputcredit"):
        return "long"
    return fallback


def _count_active_journal(out_dir: str) -> int:
    import csv as _csv

    j = os.path.join(out_dir, "micro_momo_journal.csv")
    if not os.path.exists(j):
        return 0
    try:
        with open(j, newline="", encoding="utf-8") as f:
            rows = list(_csv.DictReader(f))
        return sum(1 for r in rows if (r.get("status") or "").lower() in ("pending", "triggered"))
    except Exception:
        return 0


def _read_cfg(path: str | None) -> dict[str, Any]:
    if not path:
        return DEFAULT_CFG
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    # shallow-merge into defaults so callers can specify partials
    cfg = json.loads(json.dumps(DEFAULT_CFG))  # deep copy
    for k, v in data.items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    return cfg


def _write_csv(path: str, rows: list[dict[str, Any]], header: list[str]) -> None:
    import csv

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in header})


def run(
    cfg_path: str | None,
    input_csv: str | None,
    chains_dir: str | None,
    out_dir: str,
    emit_json: bool,
    no_files: bool,
    data_mode: str,
    providers: list[str],
    offline: bool,
    halts_source: str | None,
    auto_producers: bool = False,
    upstream_timeout_sec: int = 30,
    webhook: str | None = None,
    alerts_json_only: bool = False,
    ib_basket_out: str | None = None,
    journal_template: bool = False,
    prebuilt_scans: list[ScanRow] | None = None,
    force_live_flag: bool = False,
    session_mode: str = "auto",
) -> list[dict[str, Any]]:
    cfg = _read_cfg(cfg_path)
    # Merge runtime data config
    cfg.setdefault("data", {})
    cfg["data"].update(
        {
            "mode": data_mode or cfg["data"].get("mode", "enrich"),
            "providers": providers or cfg["data"].get("providers", ["ib", "yahoo"]),
            "offline": bool(offline),
            "halts_source": halts_source or cfg["data"].get("halts_source", "nasdaq"),
            "cache": cfg["data"].get(
                "cache", {"enabled": True, "dir": os.path.join(out_dir, ".cache"), "ttl_sec": 60}
            ),
            # new: expose artifact/chains dirs and auto‑producers toggle to sources
            "artifact_dirs": list(
                dict.fromkeys(
                    [
                        os.path.join(out_dir, ".cache"),
                        out_dir,
                    ]
                )
            ),
            "chains_dir": chains_dir,
            "auto_producers": bool(cfg["data"].get("auto_producers", False)) or bool(auto_producers),
            "upstream_timeout_sec": int(cfg["data"].get("upstream_timeout_sec", upstream_timeout_sec)),
        }
    )
    # ENV/flag overlay for live refresh
    env_force = str(os.getenv("MOMO_FORCE_LIVE", "")).lower() in ("1", "true", "yes")
    force_live = bool(env_force or force_live_flag)
    if force_live:
        # Force fetch with TTL=0 and offline disabled; preserve providers if already set
        cache_dir = cfg.get("data", {}).get("cache", {}).get("dir") or os.path.join(out_dir, ".cache")
        cfg.setdefault("data", {}).update(
            {
                "mode": "fetch",
                "providers": cfg.get("data", {}).get("providers", ["yahoo"]),
                "offline": False,
                "cache": {"enabled": True, "dir": cache_dir, "ttl_sec": 0},
            }
        )
    session_effective = (session_mode or "auto").lower()
    if session_effective not in {"auto", "rth", "premarket"}:
        session_effective = "auto"
    # Build scans list either from symbols (synthesized) or from CSV
    scans: list[ScanRow]
    if prebuilt_scans is not None:
        scans = list(prebuilt_scans)
    elif isinstance(input_csv, str) and input_csv:
        scans = load_scan_csv(input_csv)
    else:
        # Neither input CSV nor prebuilt scans provided → empty set
        scans = []
    enrich_inplace(scans, cfg)  # v1 no-op

    results: list[dict[str, Any]] = []
    base_active = _count_active_journal(out_dir)
    max_concurrent = int(cfg.get("max_concurrent", 5))

    def _neutral_structure() -> Structure:
        return Structure(
            template="Template",
            expiry=None,
            long_strike=None,
            short_strike=None,
            debit_or_credit=None,
            width=None,
            per_leg_oi_ok=False,
            per_leg_spread_pct=None,
            needs_chain=True,
            limit_price=None,
        )

    for scan in scans:
        pf = passes_filters(scan, cfg)
        comps, raw = score_components(scan, cfg)
        tier, direction = tier_and_dir(scan, raw, cfg)

        chain_rows: list[dict[str, Any]] | list[ScanRow] = []
        chain_file: str | None = None
        if chains_dir:
            best = find_latest_chain_for_symbol(chains_dir, scan.symbol)
            if best:
                chain_file = best
        if not chain_file:
            chain_file = find_chain_file_for_symbol(chains_dir, scan.symbol) if chains_dir else None
        if chain_file:
            chain_rows = load_chain_csv(chain_file)
        # Fallback to provider-fetched chain attached during enrichment
        if not chain_rows:
            cr_fetched = getattr(scan, "_chain_rows", None)
            if isinstance(cr_fetched, list) and cr_fetched:
                chain_rows = cr_fetched
        # Ensure price is usable for structure picking (prefer last_price if present)
        try:
            lp = getattr(scan, "last_price", None)
            if lp and (not getattr(scan, "price", None) or float(getattr(scan, "price", 0.0)) <= 0):
                setattr(scan, "price", float(lp))
        except Exception:
            pass
        struct = pick_structure(scan, chain_rows, direction, cfg, tier=tier)
        contracts, tp, sl = size_and_targets(struct, scan, cfg)
        trig = entry_trigger(direction, scan, cfg)

        # --- Direction/structure alignment + live/preview guard with grace + force-live ---
        sch = rth_window_tr()
        pre_window = premarket_window_tr()
        now_tr = datetime.now(TZ_TR)

        # small grace right after open to avoid neutralizing during first bars
        open_grace = timedelta(minutes=3)
        market_window = sch.open_tr <= now_tr <= sch.close_tr
        within_grace = sch.open_tr <= now_tr <= (sch.open_tr + open_grace)
        premarket_window_active = pre_window.start_tr <= now_tr < sch.open_tr
        allow_premarket = session_effective == "premarket" or (
            session_effective == "auto" and premarket_window_active
        )

        no_intraday = (
            (getattr(scan, "vwap", None) is None)
            and not (getattr(scan, "rvol_1m", 0) or 0)
            and not (getattr(scan, "rvol_5m", 0) or 0)
        )

        # sync direction to the structure we actually chose
        direction = _direction_from_structure(struct.template, direction)
        session_state = (
            "rth"
            if market_window
            else ("premarket" if allow_premarket and premarket_window_active else "closed")
        )

        if market_window:
            if no_intraday:
                if force_live:
                    # we already set cfg.data.mode=fetch & TTL=0 above; enrichment just ran with those settings
                    # if still empty, show a "warming up" trigger instead of market-closed
                    trig = (
                        f"Warming up — first bars arriving. At open: ORB→VWAP reclaim (RVOL ≥ {cfg.get('rvol_confirm_entry', 1.5)}); "
                        f"levels: orb=NA, vwap=NA"
                    )
                    # keep Template if we truly have no intraday; structures remain Template naturally
                    struct = _neutral_structure()
                    contracts, tp, sl = (0, None, None)
                elif within_grace:
                    # no force-live, but still inside grace window — be gentle
                    trig = (
                        f"Warming up (grace {int(open_grace.total_seconds() / 60)}m). ORB→VWAP reclaim (RVOL ≥ {cfg.get('rvol_confirm_entry', 1.5)}); "
                        f"levels: orb=NA, vwap=NA"
                    )
                    struct = _neutral_structure()
                    contracts, tp, sl = (0, None, None)
                else:
                    # past grace and no intraday: neutral preview
                    trig = (
                        f"Market open, but intraday unavailable — preview only. ORB→VWAP reclaim (RVOL ≥ {cfg.get('rvol_confirm_entry', 1.5)}); "
                        f"levels: orb=NA, vwap=NA"
                    )
                    struct = _neutral_structure()
                    contracts, tp, sl = (0, None, None)
            else:
                # we have live intraday — keep existing trigger/structure
                pass
        elif allow_premarket and premarket_window_active:
            if no_intraday:
                if force_live:
                    trig = f"Pre-market force-live — waiting for first prints before open {pretty_tr(sch.open_tr)}."
                else:
                    trig = f"Pre-market — waiting for first prints before open {pretty_tr(sch.open_tr)}."
                struct = _neutral_structure()
                contracts, tp, sl = (0, None, None)
            else:
                trig = f"Pre-market setup — plan ORB at {pretty_tr(sch.open_tr)} (RVOL ≥ {cfg.get('rvol_confirm_entry', 1.5)})."
        else:
            # outside RTH: keep neutral preview
            trig = (
                f"Market closed — preview only. At open: ORB→VWAP reclaim (RVOL ≥ {cfg.get('rvol_confirm_entry', 1.5)}); "
                f"levels: orb=NA, vwap=NA"
            )
            struct = _neutral_structure()
            contracts, tp, sl = (0, None, None)
        # --- end guard ---

        # Guards
        nav = float(cfg.get("sizing", {}).get("nav", 100000.0))  # type: ignore[union-attr]
        from ..core.micro_momo import _risk_proxy  # local import to avoid surface

        risk_value = _risk_proxy(struct, contracts)
        cap_breach = 1 if risk_value > 0.03 * nav else 0
        # mark overflow when admitting this row would exceed batch cap
        concurrency_guard = 1 if (base_active + len(results) + 1) > max_concurrent else 0

        res = ResultRow(
            symbol=scan.symbol,
            raw_score=round(raw, 2),
            tier=tier,
            passes_core_filter=pf,
            direction=direction,
            structure_template=struct.template,
            contracts=contracts,
            entry_trigger=trig,
            tp=tp,
            sl=sl,
            expiry=struct.expiry,
            long_strike=struct.long_strike,
            short_strike=struct.short_strike,
            debit_or_credit=struct.debit_or_credit,
            width=struct.width,
            per_leg_oi_ok=struct.per_leg_oi_ok,
            per_leg_spread_pct=(
                round(struct.per_leg_spread_pct, 4) if struct.per_leg_spread_pct is not None else None
            ),
            needs_chain=struct.needs_chain,
        )
        base = asdict(res)
        base["cap_breach"] = cap_breach
        base["concurrency_guard"] = concurrency_guard
        base["session_state"] = session_state
        # Pass-through: append any attributes present on the scan row without overwriting
        for k, v in getattr(scan, "__dict__", {}).items():
            if k in base:
                continue
            base[k] = v
        # Flatten provenance and data_errors if enrichment populated them
        prov = getattr(scan, "_provenance", None)
        if isinstance(prov, dict):
            for k, v in prov.items():
                if k not in base:
                    base[k] = v
        errs = getattr(scan, "_data_errors", None)
        if isinstance(errs, list) and errs:
            base["data_errors"] = ";".join(str(e) for e in errs)
        results.append(base)

    if emit_json:
        print(json.dumps(results, indent=2))

    # Build alerts
    alerts: list[dict[str, Any]] = []
    for r in results:
        levels = {
            "orb_high": r.get("orb_high"),
            "vwap": r.get("vwap"),
            "stop": (r.get("vwap") * 0.97 if isinstance(r.get("vwap"), (int, float)) else None),
        }
        alerts.append(
            {
                "symbol": r["symbol"],
                "direction": r["direction"],
                "trigger": r["entry_trigger"],
                "rvol_confirm": cfg.get("rvol_confirm_entry", 1.5),
                "levels": levels,
            }
        )

    # Always write alerts JSON
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "micro_momo_alerts.json"), "w", encoding="utf-8") as f:
        json.dump(alerts, f, indent=2)

    # Optional webhook
    if webhook and not alerts_json_only and not cfg.get("data", {}).get("offline", False):
        emit_alerts(alerts, webhook, dry_run=False, offline=False)

    if not no_files:
        # Write scored CSV with enrichment/provenance columns preserved
        base_cols = [
            "symbol",
            "raw_score",
            "tier",
            "passes_core_filter",
            "direction",
            "structure_template",
            "contracts",
            "entry_trigger",
            "tp",
            "sl",
            "expiry",
            "long_strike",
            "short_strike",
            "debit_or_credit",
            "width",
            "per_leg_oi_ok",
            "per_leg_spread_pct",
            "needs_chain",
            "cap_breach",
            "concurrency_guard",
        ]
        extra_cols_set: set[str] = set()
        for row in results:
            for key in row.keys():
                if key.startswith("_"):
                    continue
                if key not in base_cols:
                    extra_cols_set.add(key)
        extra_cols: list[str] = sorted(extra_cols_set)
        # Keep data_errors at the end for readability if present
        if "data_errors" in extra_cols:
            extra_cols.remove("data_errors")
            extra_cols.append("data_errors")
        scored_cols = base_cols + extra_cols
        _write_csv(os.path.join(out_dir, "micro_momo_scored.csv"), results, scored_cols)

        # Write order CSV
        orders: list[dict[str, Any]] = []
        for r in results:
            rr = ResultRow(
                symbol=r["symbol"],
                raw_score=r["raw_score"],
                tier=r["tier"],
                passes_core_filter=r["passes_core_filter"],
                direction=r["direction"],
                structure_template=r["structure_template"],
                contracts=r["contracts"],
                entry_trigger=r["entry_trigger"],
                tp=r["tp"],
                sl=r["sl"],
                expiry=r.get("expiry"),
                long_strike=r.get("long_strike"),
                short_strike=r.get("short_strike"),
                debit_or_credit=r.get("debit_or_credit"),
                width=r.get("width"),
                per_leg_oi_ok=r.get("per_leg_oi_ok", False),
                per_leg_spread_pct=r.get("per_leg_spread_pct"),
                needs_chain=r.get("needs_chain", False),
            )
            orders.append(rr.to_orders_csv())
        order_cols = [
            "symbol",
            "tier",
            "direction",
            "structure",
            "contracts",
            "expiry",
            "long_leg",
            "short_leg",
            "limit",
            "OCO_tp",
            "OCO_sl",
            "entry_trigger",
            "notes",
        ]
        orders_path = os.path.join(out_dir, "micro_momo_orders.csv")
        _write_csv(orders_path, orders, order_cols)

        # Optional IB basket export
        if ib_basket_out:
            export_ib_basket(orders, ib_basket_out)
            notes_path = os.path.splitext(ib_basket_out)[0] + "_ib_notes.txt"
            export_ib_notes(orders, notes_path)

    # Journal template (independent from no_files)
    if journal_template:
        from ..core.journal import write_journal_template

        os.makedirs(out_dir, exist_ok=True)
        write_journal_template(results, os.path.join(out_dir, "micro_momo_journal.csv"))

    return results


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="micro-momo", description="Micro-MOMO Analyzer (CSV-only v1)")
    p.add_argument("--input", required=False, help="Path to shortlist scan CSV")
    p.add_argument("--cfg", help="Path to config JSON")
    p.add_argument("--chains_dir", help="Directory with SYMBOL_YYYYMMDD.csv chain files")
    p.add_argument("--out_dir", default="out", help="Output directory for CSVs")
    p.add_argument(
        "--symbols",
        help="Comma-separated symbols (alternative to --input). When both are provided, --symbols wins.",
    )
    p.add_argument("--json", action="store_true", help="Emit results JSON to stdout")
    p.add_argument("--no-files", action="store_true", help="Skip writing CSV files")
    p.add_argument(
        "--session",
        choices=["auto", "rth", "premarket"],
        help="Session guard (auto picks based on clock; premarket allows pre-open structures)",
    )
    # v1.1 data flags
    p.add_argument("--data-mode", choices=["csv-only", "enrich", "fetch"], default="enrich")
    p.add_argument("--providers", default="ib,yahoo", help="Comma-separated providers in priority order")
    p.add_argument("--offline", action="store_true", help="Disable all live fetches and halts")
    p.add_argument("--halts-source", default="nasdaq", help="Halts source (nasdaq); ignored when --offline")
    # force-live refresh
    p.add_argument(
        "--force-live",
        action="store_true",
        help="Force live refresh: data-mode=fetch, TTL=0, offline=False (ignores stale cache)",
    )
    # auto-producers (chains/bars before providers)
    p.add_argument(
        "--auto-producers",
        action="store_true",
        help="Attempt to generate missing local artifacts (bars/chains) via in-repo scripts before using providers",
    )
    # legacy compatibility (treat as same)
    p.add_argument("--auto-upstream", action="store_true", help=argparse.SUPPRESS)
    # v1.2 outputs
    p.add_argument("--webhook", help="Webhook URL for alerts (e.g., Slack)")
    p.add_argument("--alerts-json-only", action="store_true", help="Build alerts JSON but do not POST")
    p.add_argument(
        "--ib-basket-out", help="Path to write IB Basket CSV; notes saved alongside with _ib_notes.txt suffix"
    )
    # v1.3 journal
    p.add_argument(
        "--journal-template", action="store_true", help="Write a journal template CSV (Pending rows)"
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    session_mode = (args.session or os.getenv("MOMO_SESSION") or "auto").lower()
    if session_mode not in {"auto", "rth", "premarket"}:
        session_mode = "auto"
    # allow environment/memory to backfill symbols when neither --symbols nor --input provided
    if not getattr(args, "symbols", None) and not getattr(args, "input", None):
        sym_source = os.getenv("MOMO_SYMBOLS") or ""
        if not sym_source:
            try:
                from ..core.memory import get_pref

                sym_source = get_pref("micro_momo.symbols") or ""
            except Exception:
                sym_source = ""
        if sym_source:
            alias_map = load_alias_map([os.getenv("MOMO_ALIASES_PATH") or ""])
            normalized = normalize_symbols([s for s in sym_source.split(",") if s.strip()], alias_map)
            if normalized:
                setattr(args, "symbols", ",".join(normalized))
    # friendly input validation
    if not getattr(args, "symbols", None):
        if not getattr(args, "input", None):
            print(
                "error: provide --symbols SYM1,SYM2 (or set MOMO_SYMBOLS / memory pref) or --input <scan.csv>",
                flush=True,
            )
            return 2
        else:
            if not os.path.exists(args.input):
                print(f"error: input CSV not found: {args.input}", flush=True)
                return 2
    # Build scans from --symbols when provided; otherwise, keep CSV behavior.
    # Note: when both --input and --symbols are present, --symbols takes precedence.
    scans: list[ScanRow] = []
    if getattr(args, "symbols", None):
        alias_map = load_alias_map([os.getenv("MOMO_ALIASES_PATH") or ""])  # env-provided path has priority
        syms = normalize_symbols([s for s in str(args.symbols).split(",") if s.strip()], alias_map)
        # Synthesize minimal ScanRow entries; enrichment/fetch can fill fields later.
        scans = [
            ScanRow(
                symbol=s,
                price=0.0,
                volume=0,
                rel_strength=0.0,
                short_interest=0.0,
                turnover=0.0,
                iv_rank=0.0,
                atr_pct=0.0,
                trend=0.0,
            )
            for s in syms
        ]

    # Fast path: if symbols were provided, run directly using synthesized scans without CSV.
    if scans:
        # We reuse the run() pipeline but bypass CSV loading by passing input_csv=None
        # and injecting our synthesized scans via a minimal shim.
        # Inject: temporarily monkeypatch load_scan_csv to return our scans.
        _orig = load_scan_csv

        def _fake_load_scan_csv(_path: str) -> list[ScanRow]:  # pragma: no cover (tiny shim)
            return list(scans)

        try:
            globals()["load_scan_csv"] = _fake_load_scan_csv  # type: ignore[assignment]
            run(
                cfg_path=args.cfg,
                input_csv=None,
                chains_dir=args.chains_dir,
                out_dir=args.out_dir,
                emit_json=args.json,
                no_files=args.no_files,
                data_mode=args.data_mode,
                providers=[s for s in (args.providers or "").split(",") if s],
                offline=bool(args.offline),
                halts_source=(None if args.offline else args.halts_source),
                auto_producers=bool(args.auto_producers or args.auto_upstream),
                upstream_timeout_sec=30,
                webhook=args.webhook,
                alerts_json_only=bool(args.alerts_json_only),
                ib_basket_out=args.ib_basket_out,
                journal_template=bool(args.journal_template),
                prebuilt_scans=scans,
                force_live_flag=bool(getattr(args, "force_live", False)),
                session_mode=session_mode,
            )
        finally:
            globals()["load_scan_csv"] = _orig  # restore
        return 0

    # Fallback: CSV path is required when no symbols are provided
    if not args.input:
        print("error: --input is required when --symbols is not provided", flush=True)
        return 2

    run(
        cfg_path=args.cfg,
        input_csv=args.input,
        chains_dir=args.chains_dir,
        out_dir=args.out_dir,
        emit_json=args.json,
        no_files=args.no_files,
        data_mode=args.data_mode,
        providers=[s for s in (args.providers or "").split(",") if s],
        offline=bool(args.offline),
        halts_source=(None if args.offline else args.halts_source),
        auto_producers=bool(args.auto_producers or args.auto_upstream),
        upstream_timeout_sec=30,
        webhook=args.webhook,
        alerts_json_only=bool(args.alerts_json_only),
        ib_basket_out=args.ib_basket_out,
        journal_template=bool(args.journal_template),
        force_live_flag=bool(getattr(args, "force_live", False)),
        session_mode=session_mode,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
