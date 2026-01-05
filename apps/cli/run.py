from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Any

MODULE_PATH = Path(__file__).resolve()
CLI_ROOT = MODULE_PATH.parent
REPO_ROOT = CLI_ROOT.parents[1]
LIBS_PATH = REPO_ROOT / "libs" / "py"
if str(LIBS_PATH) not in sys.path:
    sys.path.insert(0, str(LIBS_PATH))

# Ensure the Micro-MOMO adapter is registered with the PSD runtime.
import psd.plugins.micro_momo_adapter  # noqa: F401
from psd.analyzers.base import AnalyzerResult, Candidate, Signal
from psd.runtime.registry import create_analyzer


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run PSD analyzers (default: micro_momo_analyzer)."
    )
    parser.add_argument(
        "--analyzer",
        default="micro_momo_analyzer",
        help="Registered analyzer name (default: micro_momo_analyzer).",
    )
    parser.add_argument(
        "--json-only",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable JSON-only mode (defaults to true). Use --no-json-only to disable.",
    )
    parser.add_argument(
        "--full-artifacts",
        action="store_true",
        help="Request full artifact emission (files in the output directory).",
    )
    parser.add_argument(
        "--scan-csv",
        dest="scan_csv",
        help="Path to a pre-scored scan CSV (defaults to MOMO_INPUT or none).",
    )
    parser.add_argument(
        "--chains-dir",
        dest="chains_dir",
        help="Directory containing option chains (defaults to MOMO_CHAINS_DIR or none).",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        metavar="SYMBOL",
        help="Symbols to synthesize into a scan (comma separated or repeated flag).",
    )
    parser.add_argument(
        "--cfg-json",
        dest="cfg_json",
        help="Inline JSON overrides or @path to a JSON file merged into the config.",
    )
    parser.add_argument(
        "--out",
        dest="out_dir",
        default="out/micro_momo",
        help="Output directory for analyzer artifacts (default: out/micro_momo).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress non-JSON logging (sets PE_QUIET=1 for subprocesses).",
    )
    return parser


def _parse_symbols(raw: Iterable[str] | None) -> tuple[str, ...]:
    if not raw:
        return ()
    seen: list[str] = []
    for chunk in raw:
        pieces = (
            str(chunk).replace(" ", "").split(",") if "," in str(chunk) else [chunk]
        )
        for part in pieces:
            symbol = str(part).strip().upper()
            if not symbol or symbol in seen:
                continue
            seen.append(symbol)
    return tuple(seen)


def _load_cfg_json(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    text: str
    candidate_path: Path | None = None
    if value.startswith("@"):
        candidate_path = Path(value[1:]).expanduser()
    else:
        maybe_path = Path(value).expanduser()
        if maybe_path.exists():
            candidate_path = maybe_path
    if candidate_path is not None:
        if not candidate_path.exists():
            raise SystemExit(f"Configuration override not found: {candidate_path}")
        text = candidate_path.read_text(encoding="utf-8")
    else:
        text = value
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:  # pragma: no cover - argparse guards
        raise SystemExit(f"Invalid JSON for --cfg-json: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("--cfg-json must decode to a JSON object")
    return data


def _signal_to_dict(signal: Signal) -> dict[str, Any]:
    payload = asdict(signal)
    payload["tags"] = list(payload.get("tags") or [])
    metadata = payload.get("metadata")
    if metadata is not None:
        payload["metadata"] = dict(metadata)
    return payload


def _result_to_payload(
    analyzer_name: str,
    result: AnalyzerResult | None,
    json_only: bool,
    full_artifacts: bool,
) -> dict[str, Any]:
    mode = (
        "full-artifacts" if full_artifacts else "json-only" if json_only else "hybrid"
    )
    if result is None:
        return {
            "analyzer": analyzer_name,
            "mode": mode,
            "signals": [],
            "signal_count": 0,
            "summary": None,
            "artifacts": None,
            "notes": None,
        }
    notes_map = dict(result.notes or {})
    artifacts = notes_map.get("artifacts") if notes_map else None
    summary = notes_map.get("summary") if notes_map else None
    payload = {
        "analyzer": analyzer_name,
        "mode": mode,
        "signals": [_signal_to_dict(sig) for sig in result.signals],
        "signal_count": len(result.signals),
        "summary": summary,
        "artifacts": artifacts,
        "notes": notes_map or None,
    }
    return payload


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, set):
        return sorted(value)
    return str(value)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.quiet:
        os.environ.setdefault("PE_QUIET", "1")

    output_dir = Path(args.out_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    cfg_overrides = _load_cfg_json(args.cfg_json)
    symbols = _parse_symbols(args.symbols)

    analyzer_kwargs: dict[str, Any] = {
        "output_dir": str(output_dir),
        "json_only": bool(args.json_only),
        "full_artifacts": bool(args.full_artifacts),
    }
    if cfg_overrides:
        analyzer_kwargs["cfg_overrides"] = cfg_overrides
    if symbols:
        analyzer_kwargs["symbols"] = symbols
    if args.scan_csv:
        analyzer_kwargs["scan_csv"] = args.scan_csv
    if args.chains_dir:
        analyzer_kwargs["chains_dir"] = args.chains_dir

    try:
        analyzer = create_analyzer(args.analyzer, **analyzer_kwargs)
    except Exception as exc:  # pragma: no cover - defensive guard
        parser.error(f"Failed to create analyzer '{args.analyzer}': {exc}")

    candidate = Candidate(identifier="cli", payload={})
    try:
        result = analyzer.analyze(candidate)
    except Exception as exc:  # pragma: no cover - runtime guard
        raise SystemExit(f"Analyzer '{args.analyzer}' failed: {exc}") from exc

    payload = _result_to_payload(
        analyzer_name=args.analyzer,
        result=result,
        json_only=bool(args.json_only),
        full_artifacts=bool(args.full_artifacts),
    )
    json.dump(payload, sys.stdout, indent=2, sort_keys=True, default=_json_default)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
