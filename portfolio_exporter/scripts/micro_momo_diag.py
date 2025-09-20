from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from portfolio_exporter.core.fs_utils import (
    auto_chains_dir,
    auto_config,
    find_latest_chain_for_symbol,
    find_latest_file,
)
from portfolio_exporter.core.market_clock import (
    TZ_TR,
    premarket_window_tr,
    pretty_tr,
    rth_window_tr,
)
from portfolio_exporter.core.micro_momo_sources import (
    find_chain_file_for_symbol,
    load_chain_csv,
    load_minute_bars,
    load_scan_csv,
)
from portfolio_exporter.core.micro_momo_types import ChainRow
from portfolio_exporter.core.patterns import compute_patterns
from portfolio_exporter.core.providers import ib_provider, yahoo_provider
from portfolio_exporter.core.symbols import load_alias_map, normalize_symbols
from portfolio_exporter.scripts import micro_momo_analyzer as analyzer

TZ_UTC = ZoneInfo("UTC")


@dataclass
class SymbolDiagnostics:
    symbol: str
    bars_count: int
    last_bar_ts: str | None
    vwap: float | None
    rvol_1m: float
    rvol_5m: float
    chain_rows: int
    near_money_oi: int
    guard_reason: str
    bars_source: str | None
    chain_source: str | None
    session_state: str
    notes: list[str]


def _load_memory() -> dict[str, Any]:
    path = Path(".codex/memory.json")
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_pref(path: str, default: str | None = None) -> str | None:
    cur: Any = _load_memory().get("preferences", {})
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    if isinstance(cur, str):
        return cur
    return default


def _env_true(value: str | None) -> bool:
    if value is None:
        return False
    return value.lower() in {"1", "true", "yes", "on"}


def _resolve_cfg(path_arg: str | None, pe_test: bool) -> str:
    if path_arg:
        return path_arg
    env_cfg = os.getenv("MOMO_CFG")
    if env_cfg:
        return env_cfg
    auto = auto_config(
        [
            "micro_momo_config.json",
            "config/micro_momo_config.json",
            "tests/data/micro_momo_config.json" if pe_test else None,
        ]
    )
    if auto:
        return auto
    return "tests/data/micro_momo_config.json" if pe_test else "micro_momo_config.json"


def _resolve_input(path_arg: str | None, pe_test: bool) -> str | None:
    candidates: list[str | None] = [
        path_arg,
        os.getenv("MOMO_INPUT"),
    ]
    for cand in candidates:
        if cand:
            return cand
    search_dirs: list[str | None] = [
        os.getenv("MOMO_INPUT_DIR"),
        ".",
        "./data",
        "./scans",
        "./inputs",
        "tests/data" if pe_test else None,
    ]
    patterns = tuple((os.getenv("MOMO_INPUT_GLOB") or "meme_scan_*.csv").split(","))
    auto = find_latest_file([d for d in search_dirs if d], patterns)
    if auto:
        return auto
    if pe_test:
        return "tests/data/meme_scan_sample.csv"
    return None


def _resolve_symbols(args: argparse.Namespace, alias_map: dict[str, str]) -> tuple[list[str], str | None]:
    if args.symbols:
        raw = [s.strip().upper() for s in str(args.symbols).split(",") if s.strip()]
        return normalize_symbols(raw, alias_map), None
    env = os.getenv("MOMO_SYMBOLS")
    if env:
        raw = [s.strip().upper() for s in env.split(",") if s.strip()]
        return normalize_symbols(raw, alias_map), None
    mem = _get_pref("micro_momo.symbols", "") or ""
    if mem:
        raw = [s.strip().upper() for s in mem.split(",") if s.strip()]
        return normalize_symbols(raw, alias_map), None
    input_csv = _resolve_input(args.input, bool(os.getenv("PE_TEST_MODE")))
    if input_csv and Path(input_csv).exists():
        try:
            rows = load_scan_csv(input_csv)
            return [row.symbol for row in rows if row.symbol], input_csv
        except Exception:
            return [], input_csv
    return [], None


def _ensure_cache_dir(out_dir: str) -> Path:
    cache_dir = Path(out_dir) / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _cache_info(out_dir: str) -> tuple[int, list[str]]:
    cache_dir = _ensure_cache_dir(out_dir)
    entries = sorted(str(p) for p in cache_dir.glob("yahoo_*") if p.exists())
    return len(entries), entries[:8]


def _format_ts(ts: Any) -> str | None:
    if ts is None:
        return None
    try:
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(float(ts), TZ_UTC).astimezone(TZ_TR).strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(ts, str):
            if ts.isdigit():
                return (
                    datetime.fromtimestamp(float(ts), TZ_UTC).astimezone(TZ_TR).strftime("%Y-%m-%d %H:%M:%S")
                )
            # Attempt ISO parse
            try:
                dt = datetime.fromisoformat(ts)
                return dt.astimezone(TZ_TR).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                return ts
    except Exception:
        return str(ts)
    return str(ts)


def _build_effective_cfg(
    cfg_path: str | None,
    out_dir: str,
    chains_dir: str | None,
    data_mode_arg: str | None,
    providers_arg: str | None,
    offline_flag: bool,
    auto_producers_flag: bool,
    upstream_timeout: int,
    force_live_flag: bool,
    session_mode: str,
) -> dict[str, Any]:
    cfg_missing = bool(cfg_path and not Path(cfg_path).expanduser().exists())
    cfg = analyzer._read_cfg(None if cfg_missing else cfg_path)
    if cfg_missing:
        cfg["_cfg_missing"] = cfg_path
    data_cfg = cfg.setdefault("data", {})
    existing_artifacts: Sequence[str] = []
    existing = data_cfg.get("artifact_dirs")
    if isinstance(existing, (list, tuple)):
        existing_artifacts = [str(x) for x in existing if x]
    artifact_dirs = list(dict.fromkeys(list(existing_artifacts) + [os.path.join(out_dir, ".cache"), out_dir]))
    providers = [
        s
        for s in (
            providers_arg
            or os.getenv("MOMO_PROVIDERS")
            or ",".join(data_cfg.get("providers", []))
            or "ib,yahoo"
        ).split(",")
        if s
    ]
    halts_source = (
        None if offline_flag else (os.getenv("MOMO_HALTS_SOURCE") or data_cfg.get("halts_source") or "nasdaq")
    )
    data_cfg.update(
        {
            "mode": data_mode_arg or os.getenv("MOMO_DATA_MODE") or data_cfg.get("mode", "enrich"),
            "providers": providers,
            "offline": offline_flag
            or _env_true(os.getenv("MOMO_OFFLINE"))
            or bool(data_cfg.get("offline", False)),
            "halts_source": halts_source,
            "artifact_dirs": artifact_dirs,
            "chains_dir": chains_dir or data_cfg.get("chains_dir"),
            "auto_producers": bool(data_cfg.get("auto_producers", False)) or auto_producers_flag,
            "upstream_timeout_sec": int(
                os.getenv("MOMO_UPSTREAM_TIMEOUT") or data_cfg.get("upstream_timeout_sec", upstream_timeout)
            ),
        }
    )
    cache_cfg = data_cfg.get("cache") or {}
    cache_dir = cache_cfg.get("dir") or os.path.join(out_dir, ".cache")
    ttl = cache_cfg.get("ttl_sec", 60)
    cache_cfg = {"enabled": True, "dir": cache_dir, "ttl_sec": int(os.getenv("MOMO_CACHE_TTL") or ttl)}
    data_cfg["cache"] = cache_cfg
    env_force = _env_true(os.getenv("MOMO_FORCE_LIVE"))
    if env_force or force_live_flag:
        data_cfg.update(
            {
                "mode": "fetch",
                "offline": False,
                "cache": {"enabled": True, "dir": cache_dir, "ttl_sec": 0},
            }
        )
    cfg["data"] = data_cfg
    cfg["_force_live"] = env_force or force_live_flag
    cfg["_session"] = session_mode
    return cfg


def _vwap_guard(
    now_tr: datetime,
    vwap: float | None,
    rvol1: float,
    rvol5: float,
    force_live: bool,
    session_mode: str,
) -> str:
    sched = rth_window_tr()
    pre_window = premarket_window_tr()
    market_window = sched.open_tr <= now_tr <= sched.close_tr
    grace = sched.open_tr <= now_tr <= (sched.open_tr + timedelta(minutes=3))
    premarket_window_active = pre_window.start_tr <= now_tr < sched.open_tr
    allow_premarket = session_mode == "premarket" or (session_mode == "auto" and premarket_window_active)
    no_intraday = (vwap is None) and (rvol1 == 0.0) and (rvol5 == 0.0)
    if market_window:
        if not no_intraday:
            return "ok_live"
        if force_live:
            return "warming_up_force_live"
        if grace:
            return "warming_up_grace"
        return "market_open_no_intraday"
    if allow_premarket and premarket_window_active:
        if not no_intraday:
            return "premarket_ok"
        if force_live:
            return "premarket_warming_force_live"
        return "premarket_no_intraday"
    return "outside_RTH"


def _gather_bars(
    symbol: str, cfg: dict[str, Any], notes: list[str]
) -> tuple[list[dict[str, Any]], str | None]:
    data_cfg = cfg.get("data", {})
    artifact_dirs = data_cfg.get("artifact_dirs", []) or []
    bars: list[dict[str, Any]] = []
    try:
        bars = load_minute_bars(symbol, artifact_dirs)
        if bars:
            return bars, "artifact"
    except Exception as exc:
        notes.append(f"artifact_error:{exc}")
    mode = str(data_cfg.get("mode", "enrich"))
    if mode == "csv-only":
        notes.append("mode_csv_only")
        return [], None
    if bool(data_cfg.get("offline")):
        notes.append("offline_true")
        return [], None
    for prov in data_cfg.get("providers", []) or []:
        candidate: list[dict[str, Any]] = []
        if prov == "ib":
            try:
                candidate = ib_provider.get_intraday_bars(symbol, cfg)
            except Exception as exc:
                notes.append(f"ib_error:{exc}")
        elif prov == "yahoo":
            try:
                candidate = yahoo_provider.get_intraday_bars(symbol, cfg)
            except Exception as exc:
                notes.append(f"yahoo_error:{exc}")
        if candidate:
            return candidate, prov
    return [], None


def _chain_from_dataclass(rows: Sequence[ChainRow]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "strike": row.strike,
                "right": row.right,
                "oi": row.oi,
                "volume": row.volume,
                "expiry": row.expiry,
            }
        )
    return out


def _gather_chain(
    symbol: str,
    cfg: dict[str, Any],
    spot: float | None,
    chains_dir: str | None,
    notes: list[str],
) -> tuple[int, int, str | None]:
    rows: list[dict[str, Any]] = []
    source: str | None = None
    if chains_dir:
        latest = find_latest_chain_for_symbol(chains_dir, symbol)
        if not latest:
            latest = find_chain_file_for_symbol(chains_dir, symbol)
        if latest and Path(latest).exists():
            try:
                file_rows = load_chain_csv(latest)
                rows = _chain_from_dataclass(file_rows)
                source = latest
            except Exception as exc:
                notes.append(f"chain_csv_error:{exc}")
    if not rows:
        data_cfg = cfg.get("data", {})
        mode = str(data_cfg.get("mode", "enrich"))
        if mode != "csv-only" and not bool(data_cfg.get("offline")):
            for prov in data_cfg.get("providers", []) or []:
                if prov == "yahoo":
                    try:
                        rows = yahoo_provider.get_option_chain(symbol, cfg) or []
                        if rows:
                            source = "yahoo"
                            break
                    except Exception as exc:
                        notes.append(f"yahoo_chain_error:{exc}")
                elif prov == "ib":
                    try:
                        rows = ib_provider.get_option_chain(symbol, cfg) or []
                        if rows:
                            source = "ib"
                            break
                    except Exception as exc:
                        notes.append(f"ib_chain_error:{exc}")
        else:
            if mode == "csv-only":
                notes.append("mode_csv_only_chain")
            if bool(data_cfg.get("offline")):
                notes.append("offline_chain")
    total = len(rows)
    near_oi = 0
    if spot and spot > 0 and rows:
        threshold = 0.03
        for row in rows:
            try:
                strike = float(row.get("strike"))
                if strike <= 0:
                    continue
                if abs(strike - spot) / max(spot, 1e-9) <= threshold:
                    near_oi += int(float(row.get("oi", 0)))
            except Exception:
                continue
    return total, near_oi, source


def _summarize_rth() -> dict[str, str]:
    sched = rth_window_tr()
    return {
        "open_tr": pretty_tr(sched.open_tr),
        "cutoff_tr": pretty_tr(sched.no_new_signals_after_tr),
        "close_tr": pretty_tr(sched.close_tr),
        "now_tr": datetime.now(TZ_TR).strftime("%Y-%m-%d %H:%M:%S"),
    }


def _print_header(title: str) -> None:
    print(f"\n=== {title} ===")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser("micro-momo-diag")
    parser.add_argument("--symbols", help="Comma-separated symbols", default="")
    parser.add_argument("--cfg", help="Config path (defaults to auto-discovery)", default="")
    parser.add_argument("--input", help="Scan CSV path (fallback)")
    parser.add_argument("--chains_dir", help="Chains directory")
    parser.add_argument("--out_dir", default="out")
    parser.add_argument("--data-mode")
    parser.add_argument("--providers")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--auto-producers", action="store_true")
    parser.add_argument("--force-live", action="store_true")
    parser.add_argument(
        "--session", choices=["auto", "rth", "premarket"], help="Session guard for diagnostics"
    )
    args = parser.parse_args(argv)

    pe_test = bool(os.getenv("PE_TEST_MODE"))
    out_dir = args.out_dir
    cfg_path = _resolve_cfg(args.cfg, pe_test)
    chains_dir = (
        args.chains_dir
        or os.getenv("MOMO_CHAINS_DIR")
        or auto_chains_dir(
            [
                "./option_chains",
                "./chains",
                "./data/chains",
                "tests/data" if pe_test else None,
            ]
        )
    )

    alias_map = load_alias_map([os.getenv("MOMO_ALIASES_PATH") or ""])
    symbols, input_csv = _resolve_symbols(args, alias_map)
    if not symbols:
        print("no symbols resolved (set MOMO_SYMBOLS, memory preference, or pass --symbols)", flush=True)
        if input_csv and not Path(input_csv).exists():
            print(f"hint: expected input CSV {input_csv} not found", flush=True)
        return 2

    session_mode = (args.session or os.getenv("MOMO_SESSION") or "auto").lower()
    if session_mode not in {"auto", "rth", "premarket"}:
        session_mode = "auto"

    cfg = _build_effective_cfg(
        cfg_path=cfg_path,
        out_dir=out_dir,
        chains_dir=chains_dir,
        data_mode_arg=args.data_mode,
        providers_arg=args.providers,
        offline_flag=bool(args.offline),
        auto_producers_flag=bool(args.auto_producers),
        upstream_timeout=30,
        force_live_flag=bool(args.force_live),
        session_mode=session_mode,
    )

    cache_count, cache_sample = _cache_info(out_dir)

    print("=== ENV/CFG ===")
    printable_cfg = {
        "data": cfg.get("data", {}),
        "force_live": cfg.get("_force_live", False),
        "session": session_mode,
        "cfg_path": cfg_path,
        "cfg_missing": cfg.get("_cfg_missing"),
        "chains_dir": chains_dir,
        "input_csv": input_csv,
    }
    print(json.dumps(printable_cfg, indent=2, default=str))
    print(f"cache_dir: {str(Path(out_dir) / '.cache')}")
    print(f"cache_entries: {cache_count}")
    if cache_sample:
        print("cache_sample:")
        for entry in cache_sample:
            print(f"  - {entry}")

    _print_header("RTH (TR-local)")
    print(json.dumps(_summarize_rth(), indent=2))

    pre_window = premarket_window_tr()
    _print_header("SESSION")
    print(
        json.dumps(
            {
                "session_mode": session_mode,
                "premarket_start_tr": pretty_tr(pre_window.start_tr),
                "premarket_end_tr": pretty_tr(pre_window.end_tr),
            },
            indent=2,
        )
    )

    _print_header("SYMBOLS")
    print(",".join(symbols))

    results: list[SymbolDiagnostics] = []
    now_tr = datetime.now(TZ_TR)
    force_live_eff = bool(args.force_live or cfg.get("_force_live", False))

    for sym in symbols:
        notes: list[str] = []
        bars, bars_source = _gather_bars(sym, cfg, notes)
        patterns = compute_patterns(bars) if bars else {}
        vwap = patterns.get("vwap") if isinstance(patterns, dict) else None
        rvol1 = float(patterns.get("rvol_1m", 0.0)) if isinstance(patterns, dict) else 0.0
        rvol5 = float(patterns.get("rvol_5m", 0.0)) if isinstance(patterns, dict) else 0.0
        last_ts = _format_ts(bars[-1].get("ts")) if bars else None
        spot = None
        try:
            if bars:
                spot = float(bars[-1].get("close", 0.0))
        except Exception:
            spot = None
        chain_rows, near_oi, chain_source = _gather_chain(sym, cfg, spot, chains_dir, notes)
        sch = rth_window_tr()
        pre_window = premarket_window_tr()
        market_window = sch.open_tr <= now_tr <= sch.close_tr
        premarket_window_active = pre_window.start_tr <= now_tr < sch.open_tr
        allow_premarket = session_mode == "premarket" or (session_mode == "auto" and premarket_window_active)
        session_state = (
            "rth"
            if market_window
            else ("premarket" if allow_premarket and premarket_window_active else "closed")
        )
        guard = _vwap_guard(
            now_tr,
            vwap if isinstance(vwap, float) else None,
            rvol1,
            rvol5,
            force_live_eff,
            session_mode,
        )
        results.append(
            SymbolDiagnostics(
                symbol=sym,
                bars_count=len(bars),
                last_bar_ts=last_ts,
                vwap=float(vwap) if isinstance(vwap, (float, int)) else None,
                rvol_1m=rvol1,
                rvol_5m=rvol5,
                chain_rows=chain_rows,
                near_money_oi=near_oi,
                guard_reason=guard,
                bars_source=bars_source,
                chain_source=chain_source,
                session_state=session_state,
                notes=notes,
            )
        )

    _print_header("DIAG RESULTS")
    for res in results:
        payload = {
            "symbol": res.symbol,
            "bars_15m": res.bars_count,
            "last_bar_ts": res.last_bar_ts,
            "vwap": res.vwap,
            "rvol_1m": round(res.rvol_1m, 2),
            "rvol_5m": round(res.rvol_5m, 2),
            "chain_rows": res.chain_rows,
            "near_money_oi": res.near_money_oi,
            "guard_reason": res.guard_reason,
            "bars_source": res.bars_source,
            "chain_source": res.chain_source,
            "session_state": res.session_state,
        }
        if res.notes:
            payload["notes"] = res.notes
        print(json.dumps(payload, default=str))

    print(
        "\nLegend guard_reason: ok_live | warming_up_grace | warming_up_force_live | market_open_no_intraday | "
        "premarket_ok | premarket_no_intraday | premarket_warming_force_live | outside_RTH"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
