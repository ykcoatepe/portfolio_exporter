from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from typing import Any, Dict, List, Optional

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
from ..core.micro_momo_types import ResultRow, ScanRow


DEFAULT_CFG: Dict[str, Any] = {
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


def _read_cfg(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return DEFAULT_CFG
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # shallow-merge into defaults so callers can specify partials
    cfg = json.loads(json.dumps(DEFAULT_CFG))  # deep copy
    for k, v in data.items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    return cfg


def _write_csv(path: str, rows: List[Dict[str, Any]], header: List[str]) -> None:
    import csv

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in header})


def run(cfg_path: Optional[str], input_csv: str, chains_dir: Optional[str], out_dir: str, emit_json: bool, no_files: bool,
        data_mode: str, providers: List[str], offline: bool, halts_source: Optional[str]) -> List[Dict[str, Any]]:
    cfg = _read_cfg(cfg_path)
    # Merge runtime data config
    cfg.setdefault("data", {})
    cfg["data"].update({
        "mode": data_mode or cfg["data"].get("mode", "enrich"),
        "providers": providers or cfg["data"].get("providers", ["ib", "yahoo"]),
        "offline": bool(offline),
        "halts_source": halts_source or cfg["data"].get("halts_source", "nasdaq"),
        "cache": cfg["data"].get("cache", {"enabled": True, "dir": os.path.join(out_dir, ".cache"), "ttl_sec": 60}),
    })
    scans = load_scan_csv(input_csv)
    enrich_inplace(scans, cfg)  # v1 no-op

    results: List[Dict[str, Any]] = []
    for scan in scans:
        pf = passes_filters(scan, cfg)
        comps, raw = score_components(scan, cfg)
        tier, direction = tier_and_dir(scan, raw, cfg)

        chain_file = find_chain_file_for_symbol(chains_dir, scan.symbol)
        chain_rows = load_chain_csv(chain_file) if chain_file else []
        struct = pick_structure(scan, chain_rows, direction, cfg)
        contracts, tp, sl = size_and_targets(struct, scan, cfg)
        trig = entry_trigger(direction, scan, cfg)

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
            per_leg_spread_pct=(round(struct.per_leg_spread_pct, 4) if struct.per_leg_spread_pct is not None else None),
            needs_chain=struct.needs_chain,
        )
        base = asdict(res)
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

    if not no_files:
        # Write scored CSV
        scored_cols = [
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
        ]
        _write_csv(os.path.join(out_dir, "micro_momo_scored.csv"), results, scored_cols)

        # Write order CSV
        orders: List[Dict[str, Any]] = []
        for r in results:
            rr = ResultRow(**r)
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
        _write_csv(os.path.join(out_dir, "micro_momo_orders.csv"), orders, order_cols)

    return results


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="micro-momo", description="Micro-MOMO Analyzer (CSV-only v1)")
    p.add_argument("--input", required=True, help="Path to shortlist scan CSV")
    p.add_argument("--cfg", help="Path to config JSON")
    p.add_argument("--chains_dir", help="Directory with SYMBOL_YYYYMMDD.csv chain files")
    p.add_argument("--out_dir", default="out", help="Output directory for CSVs")
    p.add_argument("--json", action="store_true", help="Emit results JSON to stdout")
    p.add_argument("--no-files", action="store_true", help="Skip writing CSV files")
    # v1.1 data flags
    p.add_argument("--data-mode", choices=["csv-only", "enrich", "fetch"], default="enrich")
    p.add_argument("--providers", default="ib,yahoo", help="Comma-separated providers in priority order")
    p.add_argument("--offline", action="store_true", help="Disable all live fetches and halts")
    p.add_argument("--halts-source", default="nasdaq", help="Halts source (nasdaq); ignored when --offline")
    return p


def main(argv: List[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
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
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
