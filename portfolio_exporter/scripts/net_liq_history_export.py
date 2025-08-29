#!/usr/bin/env python3
"""Export end-of-day Net‑Liq history from TWS or Client‑Portal.

This module offers a small CLI capable of reading the local
``dailyNetLiq.csv`` written by Trader Workstation, querying the
Client‑Portal PortfolioAnalyst API, or working entirely offline via a
fixture CSV. Outputs are routed through :func:`portfolio_exporter.core.io.save`
and can be emitted as CSV, Excel, or PDF files.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

from portfolio_exporter.core import cli as cli_helpers
from portfolio_exporter.core import io as core_io
from portfolio_exporter.core import json as json_helpers
from portfolio_exporter.core.runlog import RunLog
from portfolio_exporter.core.config import settings


# ---------------------------------------------------------------------------
# data sources

TWS_EXPORT_DIR = Path(os.getenv("TWS_EXPORT_DIR", "~/Jts/Export")).expanduser()
TWS_NET_LIQ_CSV = TWS_EXPORT_DIR / "dailyNetLiq.csv"

CP_BASE = "https://localhost:5000/v1/api"
CP_TOKEN = os.getenv("CP_REFRESH_TOKEN", "")
VERIFY_SSL = False


# ---------------------------------------------------------------------------
# helpers


def _parse_dates(df: pd.DataFrame) -> pd.DataFrame:
    df.index = pd.to_datetime(df.index).date
    return df.sort_index()


def _read_tws_file() -> Optional[pd.DataFrame]:
    if not TWS_NET_LIQ_CSV.exists():
        return None
    df = pd.read_csv(TWS_NET_LIQ_CSV)
    if {"Date", "NetLiquidationByCurrency"}.issubset(df.columns):
        df = (
            df[["Date", "NetLiquidationByCurrency"]]
            .rename(columns={"NetLiquidationByCurrency": "net_liq"})
            .set_index("Date")
        )
        return _parse_dates(df)
    return None


def _pa_rest_download() -> pd.DataFrame:
    if not CP_TOKEN:
        sys.exit("❌  Set CP_REFRESH_TOKEN env-var or edit CP_TOKEN in script.")

    session = requests.Session()
    session.verify = VERIFY_SSL
    r = session.post(f"{CP_BASE}/iserver/reauthorize", json={"refreshtoken": CP_TOKEN})
    r.raise_for_status()
    params = {"acctIds": "", "fromDate": "", "toDate": "", "format": "CSV"}
    r = session.get(f"{CP_BASE}/pa/performance/timeweighted", params=params)
    r.raise_for_status()
    df_all = pd.read_csv(io.StringIO(r.text))
    if {"Date", "NetLiquidation"}.issubset(df_all.columns):
        df = (
            df_all[["Date", "NetLiquidation"]]
            .rename(columns={"NetLiquidation": "net_liq"})
            .set_index("Date")
        )
        return _parse_dates(df)
    sys.exit("❌  Unexpected column layout from PortfolioAnalyst CSV.")


def _read_fixture_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    for col in ["NetLiq", "NetLiquidation", "NetLiquidationByCurrency"]:
        if col in df.columns and "Date" in df.columns:
            df = df[["Date", col]].rename(columns={col: "net_liq"}).set_index("Date")
            return _parse_dates(df)
    sys.exit("❌  Unexpected column layout in fixture CSV.")


def _filter_range(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    if start:
        df = df[df.index >= datetime.fromisoformat(start).date()]
    if end:
        df = df[df.index <= datetime.fromisoformat(end).date()]
    return df


def _load_data(source: str, fixture_csv: Path | None) -> pd.DataFrame:
    if source == "fixture":
        if not fixture_csv:
            sys.exit("❌  --fixture-csv is required when source=fixture.")
        return _read_fixture_csv(fixture_csv)
    if source == "tws":
        df = _read_tws_file()
        if df is None:
            sys.exit("❌  dailyNetLiq.csv not found.")
        return df
    if source in {"clientportal", "cp"}:
        return _pa_rest_download()
    if source == "auto":
        # Prefer local TWS export when present
        df = _read_tws_file()
        if df is not None:
            return df
        # Then try Client Portal if token is available
        if CP_TOKEN:
            return _pa_rest_download()
        # If a fixture was explicitly provided, use it
        if fixture_csv:
            return _read_fixture_csv(fixture_csv)
        # As a developer-friendly fallback, try the repo fixture if present
        try:
            repo_root = Path(__file__).resolve().parents[2]
            candidate = repo_root / "tests/data/net_liq_fixture.csv"
            if candidate.exists():
                return _read_fixture_csv(candidate)
        except Exception:
            # Best-effort only; continue to error message below
            pass
        # No viable source found – provide actionable guidance
        sys.exit(
            "❌  No data source available. Set CP_REFRESH_TOKEN, place TWS 'dailyNetLiq.csv' "
            f"at {TWS_NET_LIQ_CSV}, or run with --source fixture --fixture-csv <path>."
        )
    sys.exit("❌  Unknown source.")


# ---------------------------------------------------------------------------
# core logic


def _run_core(
    ns: argparse.Namespace,
    formats: dict[str, bool],
    outdir: Path,
) -> tuple[pd.DataFrame, dict, list[Path]]:
    df = _load_data(ns.source, ns.fixture_csv)
    df = _filter_range(df, ns.start, ns.end)
    if df.empty:
        sys.exit("❌  No data in the selected date range.")
    df = df.rename(columns={"net_liq": "NetLiq"})

    outputs = {k: "" for k in formats}
    written: list[Path] = []
    if any(formats.values()):
        df_save = df.rename_axis("date").reset_index()
        for fmt, do in formats.items():
            if do:
                p = core_io.save(df_save, "net_liq_history_export", fmt, outdir)
                outputs[fmt] = str(p)
                written.append(p)

    summary = json_helpers.time_series_summary(
        rows=len(df),
        start=df.index.min().isoformat(),
        end=df.index.max().isoformat(),
        outputs=outputs,
    )
    return df, summary, written


def cli(ns: argparse.Namespace) -> dict:
    outdir = cli_helpers.resolve_output_dir(getattr(ns, "output_dir", None))
    defaults = {"csv": bool(getattr(ns, "output_dir", None) or os.getenv("OUTPUT_DIR") or os.getenv("PE_OUTPUT_DIR"))}
    defaults.update({"excel": False, "pdf": False})
    formats = cli_helpers.decide_file_writes(
        ns,
        json_only_default=True,
        defaults=defaults,
    )

    with RunLog(script="net_liq_history_export", args=vars(ns), output_dir=outdir) as rl:
        with rl.time("run_core"):
            df, summary, written = _run_core(ns, formats, outdir)
        if ns.debug_timings:
            summary.setdefault("meta", {})["timings"] = rl.timings
            if written:
                tpath = core_io.save(pd.DataFrame(rl.timings), "timings", "csv", outdir)
                summary["outputs"].append(str(tpath))
                written.append(tpath)
        rl.add_outputs(written)
        manifest_path = rl.finalize(write=bool(written))

    quiet, pretty = cli_helpers.resolve_quiet(ns.no_pretty)
    effective_quiet = quiet or getattr(ns, "quiet", False)
    if manifest_path:
        summary["outputs"].append(str(manifest_path))
    if not ns.json and not effective_quiet:
        df_print = df.rename_axis("date").reset_index()
        if pretty:
            from rich.console import Console

            Console().print(df_print)
        else:
            print(df_print.to_string(index=False))
    return summary

def get_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export Net-Liq history")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument(
        "--source",
        choices=["auto", "tws", "clientportal", "fixture"],
        default="auto",
    )
    parser.add_argument("--fixture-csv", type=Path)
    parser.add_argument("--csv", action="store_true")
    parser.add_argument("--pdf", action="store_true")
    cli_helpers.add_common_output_args(parser, include_excel=True)
    parser.add_argument("--quiet", action="store_true")
    cli_helpers.add_common_debug_args(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = get_arg_parser()
    args = parser.parse_args(argv)
    summary = cli(args)
    if args.json:
        quiet, _ = cli_helpers.resolve_quiet(args.no_pretty)
        cli_helpers.print_json(summary, quiet)
    return 0


def run(fmt: str = "csv", plot: bool = False) -> None:  # pragma: no cover - legacy
    ns = argparse.Namespace(
        start=None,
        end=None,
        source="auto",
        csv=(fmt == "csv"),
        excel=(fmt == "excel"),
        pdf=(fmt == "pdf"),
        output_dir=None,
        no_files=False,
        quiet=False,
        no_pretty=False,
        json=False,
        fixture_csv=None,
    )
    formats = {"csv": ns.csv, "excel": ns.excel, "pdf": ns.pdf}
    outdir = cli_helpers.resolve_output_dir(None)
    df, _summary, _written = _run_core(ns, formats, outdir)
    if plot:
        try:
            import matplotlib.pyplot as plt  # type: ignore
        except Exception:  # pragma: no cover - optional
            print("⚠️  matplotlib not installed – skipping chart.")
        else:
            df["NetLiq"].plot(title="Net Liquidation History")
            plt.show()


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
