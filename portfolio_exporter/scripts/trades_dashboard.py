#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, Dict

import pandas as pd

from portfolio_exporter.core import cli as cli_helpers
from portfolio_exporter.core import io as core_io
from portfolio_exporter.core import json as json_helpers
from portfolio_exporter.core.runlog import RunLog

try:  # optional PDF support
    from reportlab.platypus import SimpleDocTemplate, Paragraph
    from reportlab.lib.styles import getSampleStyleSheet
except Exception:  # pragma: no cover - optional
    SimpleDocTemplate = None  # type: ignore
    Paragraph = None  # type: ignore
    getSampleStyleSheet = None  # type: ignore


# ---------------------------------------------------------------------------
# data loaders


def _load_trades_report(path: Path | None) -> pd.DataFrame:
    if not path or not path.exists():
        return pd.DataFrame()
    try:
        if path.suffix == ".json":
            return pd.read_json(path)
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _load_latest_trades_report(explicit: str | None) -> pd.DataFrame:
    if explicit:
        return _load_trades_report(Path(explicit))
    p = core_io.latest_file("trades_report", "json")
    if not p:
        p = core_io.latest_file("trades_report", "csv")
    return _load_trades_report(p)


def _load_quick_chain() -> pd.DataFrame:
    p = core_io.latest_file("quick_chain", "csv")
    if not p:
        return pd.DataFrame()
    try:
        return pd.read_csv(p)
    except Exception:
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# analytics


def _summarize(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {
            "clusters": 0,
            "net_credit_debit": 0.0,
            "by_structure": {},
            "top_clusters": [],
        }
    clusters = int(df["cluster_id"].nunique()) if "cluster_id" in df.columns else len(df)
    val_col = "pnl" if "pnl" in df.columns else "credit_debit"
    net = float(df[val_col].sum()) if val_col in df.columns else 0.0
    by_structure: Dict[str, int] = {}
    if "structure" in df.columns:
        by_structure = {str(k): int(v) for k, v in df.groupby("structure").size().items()}
    top_clusters: list[dict[str, Any]] = []
    if "cluster_id" in df.columns and val_col in df.columns:
        top = (
            df.groupby(["cluster_id", "structure"], dropna=False)[val_col]
            .sum()
            .reset_index()
        )
        top = top.sort_values(val_col, key=lambda s: s.abs(), ascending=False).head(5)
        for _, row in top.iterrows():
            top_clusters.append(
                {
                    "cluster_id": int(row["cluster_id"]),
                    "pnl": float(row[val_col]),
                    "structure": row.get("structure"),
                }
            )
    return {
        "clusters": clusters,
        "net_credit_debit": net,
        "by_structure": by_structure,
        "top_clusters": top_clusters,
    }


# ---------------------------------------------------------------------------
# output builders


def _build_html(summary: Dict[str, Any]) -> str:
    by_struct_rows = "".join(
        f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in summary["by_structure"].items()
    )
    top_rows = "".join(
        f"<tr><td>{c['cluster_id']}</td><td>{c['pnl']}</td><td>{c.get('structure','')}</td></tr>"
        for c in summary["top_clusters"]
    )
    return (
        "<html><head><title>Trades Dashboard</title></head><body>"
        "<h1>Trades Dashboard</h1>"
        f"<div><p>Clusters: {summary['clusters']}</p>"
        f"<p>Net Credit/Debit: {summary['net_credit_debit']}</p></div>"
        "<h2>By Structure</h2><table>" + by_struct_rows + "</table>"
        "<h2>Top Clusters</h2><table>" + top_rows + "</table>"
        "</body></html>"
    )


def _build_pdf(summary: Dict[str, Any], path: Path) -> None:
    if SimpleDocTemplate is None or Paragraph is None or getSampleStyleSheet is None:
        raise RuntimeError("reportlab not installed")
    doc = SimpleDocTemplate(str(path))
    styles = getSampleStyleSheet()
    flow = [
        Paragraph("Trades Dashboard", styles["Heading1"]),
        Paragraph(f"Clusters: {summary['clusters']}", styles["Normal"]),
        Paragraph(f"Net Credit/Debit: {summary['net_credit_debit']}", styles["Normal"]),
    ]
    doc.build(flow)


# ---------------------------------------------------------------------------
# CLI


def get_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Trades Dashboard")
    parser.add_argument("--trades-report", help="Path to trades_report CSV/JSON", default=None)
    # Explicit flags required by tests
    parser.add_argument("--json", action="store_true", help="Print JSON summary to stdout")
    parser.add_argument("--no-files", action="store_true", help="Do not write any files")
    parser.add_argument("--output-dir", help="Directory to write outputs")
    parser.add_argument("--no-pretty", action="store_true", help="Disable pretty printing")
    parser.add_argument("--debug-timings", action="store_true", help="Emit timing breakdown")
    return parser


def main(argv: list[str] | None = None):
    parser = get_arg_parser()
    args = parser.parse_args(argv)

    quiet, pretty = cli_helpers.resolve_quiet(args.no_pretty)
    outdir = Path(args.output_dir).expanduser() if args.output_dir else None
    # Respect --no-files strictly regardless of defaults
    write_files = bool(outdir) and not args.no_files
    formats = {"html": write_files, "pdf": write_files}

    df = _load_latest_trades_report(args.trades_report)
    _ = _load_quick_chain()  # currently unused but loaded for future use
    sections = _summarize(df)
    meta: dict[str, Any] = {}

    outputs: dict[str, str] = {k: "" for k in formats}
    written: list[Path] = []

    with RunLog(script="trades_dashboard", args=vars(args), output_dir=outdir) as rl:
        if formats.get("html"):
            html = _build_html(sections)
            path_html = core_io.save(html, "trades_dashboard", "html", outdir)
            outputs["html"] = str(path_html)
            written.append(path_html)
            theme_css = (
                Path(__file__).resolve().parents[2] / "docs" / "assets" / "theme.css"
            )
            if not theme_css.exists():
                theme_css = Path(__file__).resolve().parents[1] / "assets" / "theme.css"
            if theme_css.exists() and outdir:
                try:
                    shutil.copy(theme_css, outdir / "theme.css")
                except Exception:
                    pass
        if formats.get("pdf"):
            try:
                path_pdf = core_io.save(
                    f"Trades Dashboard\nClusters: {sections['clusters']}\nNet: {sections['net_credit_debit']}",
                    "trades_dashboard",
                    "pdf",
                    outdir,
                )
            except Exception:
                path_pdf = None
            if path_pdf:
                outputs["pdf"] = str(path_pdf)
                written.append(path_pdf)
        if args.debug_timings:
            meta["timings"] = rl.timings
            if written and write_files:
                tpath = core_io.save(pd.DataFrame(rl.timings), "timings", "csv", outdir)
                outputs["timings"] = str(tpath)
                written.append(tpath)

        rl.add_outputs(written)
        manifest_path = rl.finalize(write=bool(written))
        if manifest_path:
            written.append(manifest_path)
    summary = json_helpers.report_summary(sections, outputs=outputs, meta=meta or None)
    if 'manifest_path' in locals() and manifest_path:
        summary["outputs"].append(str(manifest_path))
    if args.json:
        cli_helpers.print_json(summary, quiet)
        return 0 if argv is None else summary
    if not quiet:
        print(json.dumps(summary, indent=2 if pretty else None))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
