from pathlib import Path
import sqlite3
import pandas as pd
from .config import settings


def save(
    df: pd.DataFrame, name: str, fmt: str = "csv", outdir: str | Path | None = None
):
    outdir = Path(
        outdir
        or "/Users/yordamkocatepe/Library/Mobile Documents/com~apple~CloudDocs/Downloads"
    ).expanduser()
    outdir.mkdir(parents=True, exist_ok=True)
    fname = outdir / f"{name}.{ {'csv':'csv','excel':'xlsx','pdf':'pdf'}[fmt] }"
    if fmt == "csv":
        df.to_csv(fname, index=False)
    elif fmt == "excel":
        df.to_excel(fname, index=False)
    elif fmt == "pdf":
        import pandas as pd, reportlab  # noqa: F401 – ensure dep

        df.to_html(fname.with_suffix(".html"), index=False)
        # simple html→pdf placeholder; real impl later
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
