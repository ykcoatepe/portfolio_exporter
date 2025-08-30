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

    # Track the active instance so prompts can temporarily pause the Live area.
    current: "StatusBar | None" = None

    def __init__(self, text: str = "Ready", style: str = "green"):
        self._text = text
        self._style = style
        # Use auto_refresh=False so Rich doesn't repaint while the user types
        # into regular input() prompts. We explicitly update the bar via update().
        self._live = Live(
            self._render(), console=console, transient=False, auto_refresh=False
        )
        self._live.__enter__()  # start live context
        # expose console for menus to print via the same console
        self.console = console
        StatusBar.current = self

    # --- public API ----------------------------------------------------
    def update(self, text: str, style: str = "green") -> None:
        self._text, self._style = text, style
        self._live.update(self._render())

    def stop(self) -> None:
        self._live.__exit__(None, None, None)
        StatusBar.current = None

    # --- helpers -------------------------------------------------------
    def _render(self):
        panel = Panel(Align.left(self._text), style=self._style, padding=(0, 1))
        return panel

    # --- input helper --------------------------------------------------
    def prompt(self, prompt: str = "") -> str:
        # Temporarily suspend the live display so the terminal behaves like
        # normal input (keystrokes stay visible and don't get repainted).
        # Rich >= 13 has Live.pause(); older versions don't. Provide a
        # backwards‑compatible fallback by stop/start around the prompt.
        from builtins import input as builtin_input

        try:
            pause = getattr(self._live, "pause", None)
            if callable(pause):
                with pause():
                    return builtin_input(prompt)
        except Exception:
            # Fall through to stop/start fallback
            pass

        # Fallback for older Rich versions without Live.pause()
        try:
            if hasattr(self._live, "stop"):
                self._live.stop()
        except Exception:
            pass
        try:
            return builtin_input(prompt)
        finally:
            try:
                if hasattr(self._live, "start"):
                    self._live.start()
                else:
                    # Re-enter live context if start() is unavailable
                    self._live.__enter__()
            except Exception:
                pass
            try:
                self._live.update(self._render())
            except Exception:
                pass


def prompt_input(prompt: str = "") -> str:
    """Global helper to read input while pausing Live, if active."""
    if StatusBar.current is not None:
        return StatusBar.current.prompt(prompt)
    from builtins import input as builtin_input

    return builtin_input(prompt)


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


def banner_delta_theta(
    delta: float, theta: float, gamma: float, vega: float, cost: float
) -> None:
    """Print a colour-coded risk banner."""

    def _c(val: float, fmt: str) -> str:
        colour = "green" if val >= 0 else "red"
        return f"[{colour}]{fmt.format(val)}[/{colour}]"

    console.print(
        f"Δ {_c(delta, '{:+.1f}')}  Θ {_c(theta, '{:+.1f}')}  Γ {_c(gamma, '{:+.3f}')}  Vega {_c(vega, '{:+.1f}')}   Cost {_c(cost, '{:+.2f}')}"
    )
