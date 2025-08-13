"""Environment and data sanity checks."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import pandas as pd

from portfolio_exporter.core import cli as cli_helpers
from portfolio_exporter.core import io as core_io
from portfolio_exporter.core import json as json_helpers
from portfolio_exporter.core import schemas as pa_schemas
from portfolio_exporter.core.config import settings


def cli(ns: argparse.Namespace) -> dict[str, Any]:
    warnings: list[str] = []
    sections: dict[str, int] = {}
    ok = True

    # Env vars
    env_vars = ["OUTPUT_DIR"]
    missing = [e for e in env_vars if not os.getenv(e)]
    if missing:
        warnings.append(f"missing env vars: {', '.join(missing)}")
    sections["env"] = len(env_vars)

    # Output dir
    base = os.getenv("OUTPUT_DIR") or settings.output_dir
    outdir = Path(base).expanduser()
    try:
        outdir.mkdir(parents=True, exist_ok=True)
        test = outdir / ".pe_write_test"
        test.write_text("ok")
        test.unlink()
    except Exception as e:
        warnings.append(f"OUTPUT_DIR not writable: {e}")
        ok = False
    sections["output_dir"] = 1

    # Header checks
    checks = 0
    for name in ["positions", "totals", "combos", "trades"]:
        path = core_io.latest_file(f"portfolio_greeks_{name}")
        if path and path.exists():
            checks += 1
            try:
                df = pd.read_csv(path)
            except Exception as e:  # pragma: no cover - IO errors
                warnings.append(f"{path.name}: {e}")
                ok = False
                continue
            msgs = pa_schemas.check_headers(name, df)
            for msg in msgs:
                warnings.append(f"{path.name}: {msg}")
            if msgs and not any("pandera" in m for m in msgs):
                ok = False
    sections["headers"] = checks

    summary = json_helpers.report_summary(sections, outputs={})
    summary["warnings"].extend(warnings)
    summary["ok"] = ok
    summary["meta"]["script"] = "doctor"
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run environment checks")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-files", action="store_true")
    args = parser.parse_args(argv)
    summary = cli(args)
    if args.json:
        cli_helpers.print_json(summary, True)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
