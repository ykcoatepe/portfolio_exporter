from __future__ import annotations

from typing import Iterable, Iterator, TypeVar

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

T = TypeVar("T")


def iter_progress(iterable: Iterable[T], description: str) -> Iterator[T]:
    """Yield items from *iterable* with a Rich progress bar."""
    items = list(iterable)
    console = Console(force_terminal=True)
    progress = Progress(
        SpinnerColumn(),
        BarColumn(),
        TextColumn(description),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=True,
    )
    with progress:
        task = progress.add_task(description, total=len(items))
        for item in items:
            yield item
            progress.advance(task)
