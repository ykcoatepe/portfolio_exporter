from pathlib import Path
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
