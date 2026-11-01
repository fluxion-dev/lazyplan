"""Rich status-bar composition."""

from __future__ import annotations

from rich.text import Text

SEPARATOR = " · "


def status_bar(
    *,
    repo: str,
    plans: int,
    open_tasks: int,
    doing: int,
    attention: int = 0,
    marked: int = 0,
    status: str = "",
    source: str = "",
    filter_text: str = "",
    recent: int | None = None,
    update: str = "",
    note: str = "",
    event: str = "",
    width: int | None = None,
) -> Text:
    """Build the one-row status bar with readable, restrained chips."""
    bar = Text()
    bar.append(repo, style="bold")
    bar.append(SEPARATOR, style="dim")
    bar.append(f"{plans} plans")
    bar.append(SEPARATOR, style="dim")
    bar.append(f"{open_tasks} open")
    bar.append(SEPARATOR, style="dim")
    bar.append(f"{doing} doing")
    if attention:
        bar.append(SEPARATOR, style="dim")
        bar.append(f"attention {attention}", style="bold red")
    if marked:
        bar.append(SEPARATOR, style="dim")
        bar.append(f"marked {marked}", style="yellow")
    if status:
        bar.append(SEPARATOR, style="dim")
        bar.append(f" status {status} ", style="reverse")
    if source:
        bar.append(SEPARATOR, style="dim")
        bar.append(f" source {source} ", style="reverse")
    if filter_text:
        bar.append(SEPARATOR, style="dim")
        bar.append(f' filter "{filter_text}" ', style="reverse")
    if recent is not None:
        bar.append(SEPARATOR, style="dim")
        bar.append(f"recent {recent}", style="dim")
    if update:
        bar.append(SEPARATOR, style="dim")
        bar.append(update, style="bold yellow")
    if note:
        bar.append(" — ", style="dim")
        bar.append(note)
    if event:
        bar.append(SEPARATOR, style="dim")
        bar.append(f"last: {event}", style="dim")
    if width is not None:
        bar.truncate(max(10, width), overflow="ellipsis")
    return bar
