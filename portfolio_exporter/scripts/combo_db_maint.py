from __future__ import annotations

"""Audit and repair the combos DB."""

import argparse
import sqlite3
from pathlib import Path
from typing import Any, Dict

import pandas as pd

from portfolio_exporter.core import cli as cli_helpers
from portfolio_exporter.core import json as json_helpers
from portfolio_exporter.core import combo as combo_utils
from portfolio_exporter.core.chain import get_combo_db_path
from portfolio_exporter.core.io import migrate_combo_schema, save
from portfolio_exporter.core.runlog import RunLog


def _ensure_db(path: Path) -> Path:
    """Ensure a combos DB exists; seed with a small sample when absent."""
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE combos (
            combo_id TEXT PRIMARY KEY,
            structure TEXT,
            underlying TEXT,
            expiry TEXT,
            type TEXT,
            width REAL,
            credit_debit REAL,
            parent_combo_id TEXT,
            closed_date TEXT
        );
        CREATE TABLE combo_legs (
            combo_id TEXT,
            conid INTEGER,
            strike REAL,
            right TEXT,
            PRIMARY KEY(combo_id, conid)
        );
        """
    )
    conn.executemany(
        "INSERT INTO combos (combo_id, structure, underlying, expiry, type, width, credit_debit) VALUES (?,?,?,?,?,?,?)",
        [
            ("1", "vertical", "AAPL", "2024-01-19", None, None, None),
            ("2", None, "MSFT", "2024-02-16", "vertical", 10.0, 1.0),
        ],
    )
    conn.executemany(
        "INSERT INTO combo_legs (combo_id, conid, strike, right) VALUES (?,?,?,?)",
        [("1", 1, 150, "C"), ("1", 2, 155, "P")],
    )
    migrate_combo_schema(conn)
    conn.commit()
    conn.close()
    return path


def _load_df(path: Path) -> pd.DataFrame:
    conn = sqlite3.connect(path)
    df = pd.read_sql("SELECT * FROM combos", conn)
    conn.close()
    return df


def _analyse(df: pd.DataFrame) -> Dict[str, Any]:
    broken_mask = df["underlying"].isna() | df["structure"].isna()
    repair_mask = ~broken_mask & (
        df[["type", "width", "credit_debit"]].isna().any(axis=1)
    )
    unknown_mask = ~(broken_mask | repair_mask)
    return {
        "broken_count": int(broken_mask.sum()),
        "repairable_count": int(repair_mask.sum()),
        "unknown_count": int(unknown_mask.sum()),
        "broken_examples": df.loc[broken_mask, "combo_id"].head(3).tolist(),
        "repairable_examples": df.loc[repair_mask, "combo_id"].head(3).tolist(),
        "unknown_examples": df.loc[unknown_mask, "combo_id"].head(3).tolist(),
    }


def _fix_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.loc[out["structure"].isna(), "structure"] = "unknown"
    out.loc[out["underlying"].isna(), "underlying"] = "UNKNOWN"
    for col in ["type", "width", "credit_debit"]:
        if col in out.columns:
            if out[col].dtype == float:
                out[col] = out[col].fillna(0.0)
            else:
                out[col] = out[col].fillna("unknown")
    return out


def _run_core(ns: argparse.Namespace, outdir: Path, formats: Dict[str, bool]) -> Dict[str, Any]:
    db_path = _ensure_db(get_combo_db_path())
    written: list[Path] = []
    outputs = {"before": "", "after": ""}

    with RunLog(script="combo_db_maint", args=vars(ns), output_dir=outdir) as rl:
        if ns.fix:
            df_before = _load_df(db_path)
            stats_before = _analyse(df_before)
            if formats["csv"]:
                before_path = save(df_before, "combo_db_before", "csv", outdir)
                outputs["before"] = str(before_path)
                written.append(before_path)
            with rl.time("repair"):
                df_after = _fix_df(df_before)
                conn = sqlite3.connect(db_path)
                df_after.to_sql("combos", conn, if_exists="replace", index=False)
                migrate_combo_schema(conn)
                conn.close()
            df = df_after
        else:
            df = _load_df(db_path)

        with rl.time("analysis"):
            stats = _analyse(df)

        if ns.fix and formats["csv"]:
            after_path = save(df, "combo_db_after", "csv", outdir)
            outputs["after"] = str(after_path)
            written.append(after_path)

        sections = {
            "broken": stats["broken_count"],
            "repairable": stats["repairable_count"],
            "unknown": stats["unknown_count"],
        }
        meta = {
            "examples": {
                "broken": stats["broken_examples"],
                "repairable": stats["repairable_examples"],
                "unknown": stats["unknown_examples"],
            }
        }
        summary = json_helpers.report_summary(sections, outputs=outputs, meta=meta)

        if ns.debug_timings:
            summary.setdefault("meta", {})["timings"] = rl.timings
            if written and formats["csv"]:
                tpath = save(pd.DataFrame(rl.timings), "timings", "csv", outdir)
                summary["outputs"].append(str(tpath))
                written.append(tpath)

        rl.add_outputs(written)
        manifest = rl.finalize(write=bool(written))

    if manifest:
        summary["outputs"].append(str(manifest))
    return summary


def cli(ns: argparse.Namespace) -> Dict[str, Any]:
    outdir = cli_helpers.resolve_output_dir(ns.output_dir)
    formats = cli_helpers.decide_file_writes(ns, json_only_default=True, defaults={"csv": True})
    return _run_core(ns, outdir, formats)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit/repair combos DB")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-files", action="store_true")
    parser.add_argument("--output-dir")
    parser.add_argument("--no-pretty", action="store_true")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check-only", action="store_true")
    group.add_argument("--fix", action="store_true")
    parser.add_argument("--debug-timings", action="store_true")
    ns = parser.parse_args(argv)
    if not ns.fix:
        ns.check_only = True
    summary = cli(ns)
    if ns.json:
        quiet, _ = cli_helpers.resolve_quiet(ns.no_pretty)
        cli_helpers.print_json(summary, quiet)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
