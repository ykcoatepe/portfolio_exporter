from rich.live import Live
from rich.panel import Panel
from rich.align import Align
from rich.console import Console

console = Console()


class StatusBar:
    """Singleton Rich.Live status bar shown at the bottom of the TUI."""

    def __init__(self, text: str = "Ready", style: str = "green"):
        self._text = text
        self._style = style
        self._live = Live(self._render(), console=console, transient=False)
        self._live.__enter__()  # start live context

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
