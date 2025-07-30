from pathlib import Path
import pandas as pd


def save(
    df: pd.DataFrame, name: str, fmt: str = "csv", outdir: str | Path | None = None
):
    outdir = Path(
        outdir or "/Users/yordamkocatepe/Library/Mobile Documents/com~apple~CloudDocs/Downloads"
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
