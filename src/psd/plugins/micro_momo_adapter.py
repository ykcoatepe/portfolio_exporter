from __future__ import annotations

import importlib
import io
import json
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager, redirect_stdout
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from psd.analyzers.base import Analyzer, AnalyzerResult, Candidate, Signal
from psd.runtime import analyzer_factory

_STRENGTH_KEYS: tuple[str, ...] = ("rvol", "rvol_1m", "rvol_5m", "raw_score")
_ARTIFACT_MAP: dict[str, str] = {
    "micro_momo_scored.csv": "scored_csv",
    "micro_momo_orders.csv": "orders_csv",
    "micro_momo_journal.json": "journal_json",
    "micro_momo_journal.csv": "journal_csv",
    "micro_momo_basket.csv": "basket_csv",
    "micro_momo_dashboard.html": "dashboard_html",
}


@dataclass(frozen=True, slots=True)
class MicroMomoArgs:
    """Configuration applied when invoking the Micro-MOMO analyzer."""

    symbols: tuple[str, ...] = ()
    scan_csv: str | None = None
    chains_dir: str | None = None
    output_dir: str = "out"
    json_only: bool = True
    full_artifacts: bool = False
    cfg_overrides: Mapping[str, Any] | str | os.PathLike[str] | None = None
    env_overrides: Mapping[str, str | None] = field(default_factory=dict)


class MicroMomoAnalyzer(Analyzer):
    """Adapter that exposes Micro-MOMO results via the PSD analyzer protocol."""

    name = "micro_momo"

    def __init__(self, args: MicroMomoArgs) -> None:
        self._base_args = args
        self._module = None

    def analyze(self, candidate: Candidate) -> AnalyzerResult | None:
        args = self._resolve_args(candidate)
        module = self._load_module()
        results, summary_source = self._invoke(module, args)
        summary = self._build_summary(results, args, summary_source)
        psd_candidates = self._to_psd_candidates(results)
        signals = self._build_signals(results)
        artifacts = self._collect_artifacts(args) if args.full_artifacts else {}
        notes: dict[str, Any] = {
            "summary": summary,
            "candidates": psd_candidates,
            "input": {
                "candidate": candidate.identifier,
                "symbols": args.symbols,
                "scan_csv": args.scan_csv,
                "chains_dir": args.chains_dir,
                "output_dir": args.output_dir,
                "json_only": args.json_only,
                "full_artifacts": args.full_artifacts,
            },
        }
        if artifacts:
            notes["artifacts"] = artifacts
        if args.cfg_overrides:
            notes["summary"]["cfg_overrides"] = args.cfg_overrides
        return AnalyzerResult(signals=signals, notes=notes)

    # -- plumbing -----------------------------------------------------------------

    def _resolve_args(self, candidate: Candidate) -> MicroMomoArgs:
        payload = candidate.payload if isinstance(candidate.payload, Mapping) else {}
        overrides: dict[str, Any] = {}
        if payload:
            if "symbols" in payload and payload["symbols"] is not None:
                overrides["symbols"] = _as_symbols(payload["symbols"])
            if "scan_csv" in payload:
                overrides["scan_csv"] = payload["scan_csv"]
            if "chains_dir" in payload:
                overrides["chains_dir"] = payload["chains_dir"]
            if "output_dir" in payload:
                overrides["output_dir"] = payload["output_dir"]
            if "json_only" in payload:
                overrides["json_only"] = bool(payload["json_only"])
            if "full_artifacts" in payload:
                overrides["full_artifacts"] = bool(payload["full_artifacts"])
            if "cfg_overrides" in payload:
                overrides["cfg_overrides"] = payload["cfg_overrides"]
            if "env_overrides" in payload:
                overrides["env_overrides"] = payload["env_overrides"]
        merged_env = _merge_env(
            self._base_args.env_overrides, overrides.pop("env_overrides", None)
        )
        merged_symbols = overrides.pop("symbols", None)
        base = self._base_args
        resolved = replace(
            base,
            **{
                **{k: overrides[k] for k in overrides},
                **({"symbols": merged_symbols} if merged_symbols is not None else {}),
                "env_overrides": merged_env,
            },
        )
        return resolved

    def _load_module(self):
        if self._module is None:
            self._module = importlib.import_module(
                "portfolio_exporter.scripts.micro_momo_analyzer"
            )
        return self._module

    def _invoke(
        self, module: Any, args: MicroMomoArgs
    ) -> tuple[list[dict[str, Any]], Mapping[str, Any] | None]:
        cfg_path = _prepare_cfg_overrides(args.cfg_overrides, args.output_dir)
        env_updates = _build_env_updates(args, cfg_path)
        run_callable = _select_callable(module)
        summary_source: Mapping[str, Any] | None = None
        if args.output_dir:
            Path(args.output_dir).mkdir(parents=True, exist_ok=True)
        try:
            with _patched_environ(env_updates):
                if run_callable:
                    results = self._call_run(run_callable, args, cfg_path)
                else:
                    results = self._call_main(module, args, cfg_path)
        finally:
            if cfg_path:
                try:
                    os.remove(cfg_path)
                except OSError:
                    pass
        if not results:
            summary_source = _load_summary_payload(args.output_dir)
            if summary_source and isinstance(summary_source.get("candidates"), list):
                results = _results_from_summary(summary_source["candidates"])
        return results, summary_source

    def _call_run(
        self,
        run_func: Callable[..., list[dict[str, Any]]],
        args: MicroMomoArgs,
        cfg_path: str | None,
    ) -> list[dict[str, Any]]:
        prebuilt_scans = _build_prebuilt_scans(args.symbols)
        offline = (
            _truthy(args.env_overrides.get("MOMO_OFFLINE"))
            if args.env_overrides
            else None
        )
        if offline is None:
            offline = args.json_only
        data_mode = (
            args.env_overrides.get("MOMO_DATA_MODE") if args.env_overrides else None
        )
        if not data_mode:
            data_mode = "offline" if offline else "enrich"
        halts_source = (
            None if offline else args.env_overrides.get("MOMO_HALTS_SOURCE", "nasdaq")
        )
        providers = (
            _split_csv(args.env_overrides.get("MOMO_PROVIDERS"))
            if args.env_overrides
            else []
        )
        cfg_arg = cfg_path or (
            args.env_overrides.get("MOMO_CFG") if args.env_overrides else None
        )
        raw_results = run_func(
            cfg_path=cfg_arg,
            input_csv=None if args.symbols else args.scan_csv,
            chains_dir=args.chains_dir,
            out_dir=args.output_dir,
            emit_json=False,
            no_files=not args.full_artifacts,
            data_mode=data_mode,
            providers=providers,
            offline=bool(offline),
            halts_source=halts_source,
            auto_producers=(
                _truthy(args.env_overrides.get("MOMO_AUTO_PRODUCERS"))
                if args.env_overrides
                else False
            ),
            upstream_timeout_sec=30,
            webhook=(
                args.env_overrides.get("MOMO_WEBHOOK") if args.env_overrides else None
            ),
            alerts_json_only=bool(args.json_only),
            ib_basket_out=None,
            journal_template=False,
            prebuilt_scans=prebuilt_scans,
            force_live_flag=(
                _truthy(args.env_overrides.get("MOMO_FORCE_LIVE"))
                if args.env_overrides
                else False
            ),
            session_mode=(
                args.env_overrides.get("MOMO_SESSION", "auto")
                if args.env_overrides
                else "auto"
            ),
        )
        if raw_results is None:
            return []
        return list(raw_results)

    def _call_main(
        self, module: Any, args: MicroMomoArgs, cfg_path: str | None
    ) -> list[dict[str, Any]]:
        argv = _build_cli_argv(args, cfg_path)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = module.main(argv)
        if rc != 0:
            raise RuntimeError(f"micro_momo analyzer failed with exit code {rc}")
        text = buf.getvalue().strip()
        results = _parse_stdout_json(text)
        return results

    def _build_summary(
        self,
        results: list[dict[str, Any]],
        args: MicroMomoArgs,
        summary_source: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        if summary_source:
            summary = dict(summary_source)
            summary.setdefault("generated_at", datetime.now(UTC).isoformat())
            summary.setdefault(
                "mode", "full-artifacts" if args.full_artifacts else "json-only"
            )
            summary["count"] = len(summary.get("candidates", []))
            return summary
        now = datetime.now(UTC).isoformat()
        summary_candidates = []
        for row in results:
            summary_candidates.append(
                {
                    "symbol": row.get("symbol"),
                    "tier": row.get("tier"),
                    "direction": row.get("direction"),
                    "score": _safe_float(row.get("raw_score")),
                    "strength": _select_strength(row),
                    "passes_filter": _to_bool(row.get("passes_core_filter")),
                    "session": row.get("session_state"),
                    "triggers": _filter_truthy(
                        {
                            "entry": row.get("entry_trigger"),
                            "tp": row.get("tp"),
                            "sl": row.get("sl"),
                            "vwap": row.get("vwap"),
                            "orb_high": row.get("orb_high"),
                        }
                    ),
                }
            )
        return {
            "generated_at": now,
            "mode": "full-artifacts" if args.full_artifacts else "json-only",
            "count": len(results),
            "candidates": summary_candidates,
        }

    def _to_psd_candidates(
        self, results: list[dict[str, Any]]
    ) -> tuple[Candidate, ...]:
        psd_candidates = []
        for index, row in enumerate(
            sorted(results, key=lambda r: r.get("symbol") or "")
        ):
            identifier = str(row.get("symbol") or f"candidate-{index}")
            context = {
                "tier": row.get("tier"),
                "direction": row.get("direction"),
                "session": row.get("session_state"),
            }
            psd_candidates.append(
                Candidate(identifier=identifier, payload=dict(row), context=context)
            )
        return tuple(psd_candidates)

    def _build_signals(self, results: list[dict[str, Any]]) -> tuple[Signal, ...]:
        signals: list[Signal] = []
        for row in sorted(results, key=lambda r: r.get("symbol") or ""):
            identifier = str(row.get("symbol") or "")
            strength = _select_strength(row)
            tags = _build_tags(row)
            metadata = {
                "tier": row.get("tier"),
                "direction": row.get("direction"),
                "session": row.get("session_state"),
                "structure": _filter_truthy(
                    {
                        "template": row.get("structure_template"),
                        "expiry": row.get("expiry"),
                        "long": row.get("long_strike"),
                        "short": row.get("short_strike"),
                        "width": row.get("width"),
                        "contracts": row.get("contracts"),
                    }
                ),
                "triggers": _filter_truthy(
                    {
                        "entry": row.get("entry_trigger"),
                        "tp": row.get("tp"),
                        "sl": row.get("sl"),
                        "orb": row.get("orb_high"),
                        "vwap": row.get("vwap"),
                    }
                ),
            }
            if row.get("data_errors"):
                metadata["data_errors"] = row.get("data_errors")
            signals.append(
                Signal(
                    name=f"micro-momo/{identifier}" if identifier else "micro-momo",
                    value={
                        "symbol": row.get("symbol"),
                        "direction": row.get("direction"),
                        "score": _safe_float(row.get("raw_score")),
                        "tier": row.get("tier"),
                        "session": row.get("session_state"),
                    },
                    score=strength,
                    tags=tags,
                    metadata=metadata,
                )
            )
        return tuple(signals)

    def _collect_artifacts(self, args: MicroMomoArgs) -> dict[str, str]:
        base = Path(args.output_dir)
        artifacts: dict[str, str] = {}
        for filename, key in _ARTIFACT_MAP.items():
            path = base / filename
            if path.exists():
                artifacts[key] = str(path)
        return artifacts


# -- helpers ----------------------------------------------------------------------


def _as_symbols(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        parts = value.split(",")
    else:
        parts = value
    seen: list[str] = []
    for part in parts:
        symbol = str(part).strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.append(symbol)
    return tuple(seen)


def _merge_env(
    base: Mapping[str, str | None] | None,
    extra: Mapping[str, str | None] | None,
) -> dict[str, str | None]:
    merged: dict[str, str | None] = {}
    if base:
        merged.update(base)
    if extra:
        merged.update(extra)
    return merged


def _prepare_cfg_overrides(
    cfg_overrides: Mapping[str, Any] | str | os.PathLike[str] | None, output_dir: str
) -> str | None:
    if not cfg_overrides:
        return None
    if isinstance(cfg_overrides, (str, os.PathLike)):
        return str(Path(cfg_overrides))
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    fd, path = tempfile.mkstemp(
        prefix="micro_momo_cfg_", suffix=".json", dir=output_dir
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(cfg_overrides, fh, indent=2, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
    except Exception:
        os.close(fd)
        os.remove(path)
        raise
    return path


def _build_env_updates(
    args: MicroMomoArgs, cfg_path: str | None
) -> dict[str, str | None]:
    updates: dict[str, str | None] = {}
    if args.scan_csv:
        updates["MOMO_INPUT"] = args.scan_csv
    if args.chains_dir:
        updates["MOMO_CHAINS_DIR"] = args.chains_dir
    if args.output_dir:
        updates["MOMO_OUT"] = args.output_dir
    if args.json_only:
        updates.setdefault("MOMO_OFFLINE", "1")
        updates.setdefault("MOMO_DATA_MODE", "offline")
    if cfg_path:
        updates["MOMO_CFG"] = cfg_path
    if args.env_overrides:
        updates.update(args.env_overrides)
    return updates


def _select_callable(module: Any) -> Callable[..., list[dict[str, Any]]] | None:
    for name in ("run", "analyze", "main_run"):
        candidate = getattr(module, name, None)
        if callable(candidate):
            return candidate
    return None


def _build_prebuilt_scans(symbols: Sequence[str]) -> list[Any] | None:
    if not symbols:
        return None
    from portfolio_exporter.core.micro_momo_types import ScanRow

    scans = []
    for sym in symbols:
        scans.append(
            ScanRow(
                symbol=sym,
                price=0.0,
                volume=0,
                rel_strength=0.0,
                short_interest=0.0,
                turnover=0.0,
                iv_rank=0.0,
                atr_pct=0.0,
                trend=0.0,
            )
        )
    return scans


def _results_from_summary(
    candidates: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cand in candidates:
        triggers = cand.get("triggers") or {}
        row = {
            "symbol": cand.get("symbol"),
            "tier": cand.get("tier"),
            "direction": cand.get("direction"),
            "raw_score": cand.get("score"),
            "rvol": cand.get("strength"),
            "passes_core_filter": cand.get("passes_filter"),
            "session_state": cand.get("session"),
            "entry_trigger": triggers.get("entry"),
            "tp": triggers.get("tp"),
            "sl": triggers.get("sl"),
            "vwap": triggers.get("vwap"),
            "orb_high": triggers.get("orb_high"),
        }
        rows.append(row)
    return rows


def _load_summary_payload(output_dir: str | None) -> Mapping[str, Any] | None:
    if not output_dir:
        return None
    base = Path(output_dir)
    try:
        candidates = [p for p in base.glob("*summary*.json") if p.is_file()]
    except Exception:
        return None
    entries: list[tuple[float, Path]] = []
    for path in candidates:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        entries.append((mtime, path))
    for _, path in sorted(entries, key=lambda item: item[0], reverse=True):
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue
        if isinstance(data, Mapping) and isinstance(data.get("candidates"), list):
            payload = dict(data)
            payload.setdefault("source_path", str(path))
            return payload
    return None


@contextmanager
def _patched_environ(updates: Mapping[str, str | None]):
    original: dict[str, str] = {}
    removed: set[str] = set()
    try:
        for key, value in updates.items():
            if value is None:
                if key in os.environ:
                    original[key] = os.environ.pop(key)
                else:
                    removed.add(key)
            else:
                if key in os.environ:
                    original[key] = os.environ[key]
                else:
                    removed.add(key)
                os.environ[key] = str(value)
        yield
    finally:
        for key in updates:
            if key in original:
                os.environ[key] = original[key]
            elif key in removed and key in os.environ:
                os.environ.pop(key, None)


def _build_cli_argv(args: MicroMomoArgs, cfg_path: str | None) -> list[str]:
    argv: list[str] = ["--out_dir", args.output_dir]
    if cfg_path:
        argv += ["--cfg", cfg_path]
    elif args.env_overrides and args.env_overrides.get("MOMO_CFG"):
        argv += ["--cfg", str(args.env_overrides["MOMO_CFG"])]
    if args.scan_csv and not args.symbols:
        argv += ["--input", args.scan_csv]
    if args.chains_dir:
        argv += ["--chains_dir", args.chains_dir]
    if args.symbols:
        argv += ["--symbols", ",".join(args.symbols)]
    if args.json_only:
        argv += ["--json", "--no-files", "--offline", "--data-mode", "offline"]
    else:
        data_mode = (
            args.env_overrides.get("MOMO_DATA_MODE") if args.env_overrides else None
        )
        if data_mode:
            argv += ["--data-mode", data_mode]
        if _truthy(
            args.env_overrides.get("MOMO_OFFLINE") if args.env_overrides else None
        ):
            argv.append("--offline")
    return argv


def _parse_stdout_json(text: str) -> list[dict[str, Any]]:
    if not text:
        return []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in reversed(lines):
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            return list(data)
    raise RuntimeError("micro_momo analyzer did not emit JSON output")


def _select_strength(row: Mapping[str, Any]) -> float | None:
    for key in _STRENGTH_KEYS:
        strength = _safe_float(row.get(key))
        if strength is not None:
            return strength
    return None


def _build_tags(row: Mapping[str, Any]) -> tuple[str, ...]:
    tags = []
    tier = row.get("tier")
    direction = row.get("direction")
    session = row.get("session_state")
    if tier:
        tags.append(f"tier:{tier}")
    if direction:
        tags.append(f"direction:{direction}")
    if session:
        tags.append(f"session:{session}")
    return tuple(sorted(set(tags)))


def _safe_float(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value: Any) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    lower = str(value).strip().lower()
    if lower in {"1", "true", "yes", "y"}:
        return True
    if lower in {"0", "false", "no", "n"}:
        return False
    return None


def _truthy(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _split_csv(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        items = value.split(",")
    else:
        items = value
    return [str(item).strip() for item in items if str(item).strip()]


def _filter_truthy(values: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in values.items() if v not in (None, "")}


@analyzer_factory("micro_momo_analyzer", replace=True)
def _factory(args: MicroMomoArgs | None = None, **kwargs: Any) -> MicroMomoAnalyzer:
    if args is not None:
        if kwargs:
            raise ValueError(
                "Cannot provide MicroMomoArgs and additional keyword arguments"
            )
        return MicroMomoAnalyzer(args)
    allowed = {
        "symbols",
        "scan_csv",
        "chains_dir",
        "output_dir",
        "json_only",
        "full_artifacts",
        "cfg_overrides",
        "env_overrides",
    }
    unknown = set(kwargs) - allowed
    if unknown:
        raise TypeError(
            f"Unexpected arguments for micro_momo_analyzer factory: {sorted(unknown)}"
        )
    symbols_value = kwargs.pop("symbols", ())
    scan_csv = kwargs.pop("scan_csv", None)
    chains_dir = kwargs.pop("chains_dir", None)
    output_dir = kwargs.pop("output_dir", "out")
    if isinstance(scan_csv, (Path, os.PathLike)):
        scan_csv = str(scan_csv)
    if isinstance(chains_dir, (Path, os.PathLike)):
        chains_dir = str(chains_dir)
    if isinstance(output_dir, (Path, os.PathLike)):
        output_dir = str(output_dir)
    json_only = bool(kwargs.pop("json_only", True))
    full_artifacts = bool(kwargs.pop("full_artifacts", False))
    cfg_overrides = kwargs.pop("cfg_overrides", None)
    env_overrides_value = kwargs.pop("env_overrides", None)
    if kwargs:
        raise TypeError(f"Unhandled parameters: {sorted(kwargs)}")
    env_overrides = dict(env_overrides_value or {})
    args_obj = MicroMomoArgs(
        symbols=_as_symbols(symbols_value),
        scan_csv=scan_csv,
        chains_dir=chains_dir,
        output_dir=output_dir,
        json_only=json_only,
        full_artifacts=full_artifacts,
        cfg_overrides=cfg_overrides,
        env_overrides=env_overrides,
    )
    return MicroMomoAnalyzer(args_obj)


__all__ = ["MicroMomoArgs", "MicroMomoAnalyzer"]
