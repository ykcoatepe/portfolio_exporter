from pathlib import Path
import sqlite3
import json
import pandas as pd
from .config import settings


def save(
    obj: pd.DataFrame | dict | list | str,
    name: str,
    fmt: str = "csv",
    outdir: str | Path | None = None,
) -> Path:
    """Persist *obj* to *outdir* in the given *fmt*.

    Parameters
    ----------
    obj:
        DataFrame, JSON-serializable object, HTML string, or a list of
        ReportLab flowables for PDFs.
    name:
        Base filename without extension.
    fmt:
        One of ``csv``, ``excel``, ``html``, ``pdf``, or ``json``.
    outdir:
        Destination directory; defaults to :data:`settings.output_dir`.
    """

    outdir = Path(outdir or settings.output_dir).expanduser()
    outdir.mkdir(parents=True, exist_ok=True)
    ext_map = {"csv": "csv", "excel": "xlsx", "pdf": "pdf", "json": "json", "html": "html"}
    fname = outdir / f"{name}.{ext_map[fmt]}"
    if fmt == "csv":
        assert isinstance(obj, pd.DataFrame)
        obj.to_csv(fname, index=False)
    elif fmt == "excel":
        assert isinstance(obj, pd.DataFrame)
        obj.to_excel(fname, index=False)
    elif fmt == "html":
        if isinstance(obj, str):
            fname.write_text(obj)
        else:
            assert isinstance(obj, pd.DataFrame)
            obj.to_html(fname, index=False)
    elif fmt == "pdf":
        try:
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Table
        except Exception:
            fname.write_bytes(b"%PDF-1.4\n%EOF\n")
        else:
            doc = SimpleDocTemplate(str(fname))
            if isinstance(obj, list):
                doc.build(obj)
            elif isinstance(obj, str):
                styles = getSampleStyleSheet()
                doc.build([Paragraph(obj, styles["Normal"])])
            else:
                assert isinstance(obj, pd.DataFrame)
                data = [obj.columns.tolist()] + obj.astype(str).values.tolist()
                table = Table(data)
                doc.build([table])
    elif fmt == "json":
        with fname.open("w") as fh:
            json.dump(obj, fh, indent=2)
    return fname


def latest_file(
    name: str, fmt: str = "csv", outdir: str | Path | None = None
) -> Path | None:
    """Return most recent file for *name* and *fmt* in *outdir*.

    Parameters
    ----------
    name:
        Base file name without timestamp suffix.
    fmt:
        File format extension, e.g. ``"csv"``.
    outdir:
        Directory to search; defaults to settings.output_dir.

    Returns
    -------
    pathlib.Path | None
        Path to most recent matching file or ``None`` if none found.
    """

    outdir = Path(outdir or settings.output_dir).expanduser()
    pattern = f"{name}*.{fmt}"
    files = sorted(outdir.glob(pattern))
    return files[-1] if files else None


def migrate_combo_schema(conn: sqlite3.Connection) -> None:
    """Ensure combo table has latest columns."""

    cols = {row[1] for row in conn.execute("PRAGMA table_info(combos)")}
    alters = {
        "type": "ALTER TABLE combos ADD COLUMN type TEXT",
        "width": "ALTER TABLE combos ADD COLUMN width REAL",
        "credit_debit": "ALTER TABLE combos ADD COLUMN credit_debit REAL",
        "parent_combo_id": "ALTER TABLE combos ADD COLUMN parent_combo_id TEXT",
        "closed_date": "ALTER TABLE combos ADD COLUMN closed_date TEXT",
    }
    for col, ddl in alters.items():
        if col not in cols:
            conn.execute(ddl)
    conn.commit()
