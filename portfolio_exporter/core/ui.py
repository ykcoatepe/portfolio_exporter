from contextlib import contextmanager
import os
import sys

from rich.align import Align
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

import pandas as pd

console = Console()


class StatusBar:
    """Singleton Rich.Live status bar shown at the bottom of the TUI."""

    def __init__(self, text: str = "Ready", style: str = "green"):
        self._text = text
        self._style = style
        self._live = Live(self._render(), console=console, transient=False)
        self._live.__enter__()  # start live context
        # expose console for menus to print via the same console
        self.console = console

    # --- public API ----------------------------------------------------
    def update(self, text: str, style: str = "green") -> None:
        self._text, self._style = text, style
        self._live.update(self._render())

    def stop(self) -> None:
        self._live.__exit__(None, None, None)

    # --- helpers -------------------------------------------------------
    def _render(self):
        panel = Panel(Align.left(self._text), style=self._style, padding=(0, 1))
        return panel


def render_chain(df: pd.DataFrame, console: Console, width: int) -> Table:
    """Render a Rich table for an option chain snapshot.

    The ``mid`` column is coloured green when it increases from the previous
    render and red when it decreases. ``NaN`` values in greeks are shown as
    ``"--"``.
    """

    if not hasattr(render_chain, "_last_mid"):
        render_chain._last_mid = {}
    last_mid: dict[tuple[float, str], float] = render_chain._last_mid  # type: ignore[attr-defined]

    tbl = Table()
    tbl.add_column("Strike", justify="right")
    tbl.add_column("Bid", justify="right")
    tbl.add_column("Ask", justify="right")
    tbl.add_column("Mid", justify="right")
    tbl.add_column("Δ", justify="right")
    tbl.add_column("Θ", justify="right")
    tbl.add_column("IV", justify="right")

    def _fmt(val: float) -> str:
        return f"{val:.2f}" if pd.notna(val) else "--"

    for row in df.itertuples():
        key = (row.strike, row.right)
        mid = row.mid
        prev = last_mid.get(key)
        style = ""
        if prev is not None and pd.notna(mid):
            if mid > prev:
                style = "green"
            elif mid < prev:
                style = "red"
        last_mid[key] = mid

        tbl.add_row(
            f"{row.strike:g}",
            _fmt(row.bid),
            _fmt(row.ask),
            f"[{style}]{_fmt(mid)}[/{style}]" if style else _fmt(mid),
            _fmt(row.delta),
            _fmt(row.theta),
            _fmt(row.iv),
        )

    return tbl


def _progress_console() -> Console:
    return Console(force_terminal=not sys.stdin.isatty())


@contextmanager
def spinner(msg: str):
    if os.getenv("PE_QUIET", "0").lower() in {"1", "true", "yes"}:
        yield
        return
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=_progress_console(),
    ) as prog:
        prog.add_task(description=msg, total=None)
        yield


def run_with_spinner(msg: str, fn, *a, **kw):
    with spinner(msg):
        return fn(*a, **kw)
