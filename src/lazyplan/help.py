"""Help text and key hints derived from the palette registry."""

from __future__ import annotations

from .palette import COMMANDS

NAV_ROWS: tuple[tuple[str, str], ...] = (
    ("j/k, up/down, click", "move cursor / select"),
    ("left/right, click arrow", "fold / unfold row"),
    ("escape", "clear filter / back"),
)

#: One-line hint bar: (key, short label) in reading order.
HINT_ITEMS: tuple[tuple[str, str], ...] = (
    ("n", "new"),
    ("e", "edit"),
    ("s", "status"),
    ("x", "tick"),
    ("d", "delete"),
    ("/", "filter"),
    ("g", "source"),
    ("?", "help"),
    ("c", "commands"),
)

HELP_GROUPS: tuple[str, ...] = ("MOVE", "CHANGE", "FIND", "APP")
_HELP_WIDTH = 20


def keymap() -> tuple[tuple[str, str, str], ...]:
    """Canonical key table: direct keys from commands plus navigation."""
    rows: list[tuple[str, str, str]] = [(key, hint, "tree") for key, hint in NAV_ROWS]
    for cmd in COMMANDS:
        key = cmd.key or cmd.help_key
        if key:
            rows.append((key, cmd.help_hint or cmd.label.lower(), "tree"))
    return tuple(rows)


def _help_rows(group: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if group == "MOVE":
        rows.extend(NAV_ROWS)
    rows.extend(
        (cmd.help_key or cmd.key, cmd.help_hint or cmd.label.lower())
        for cmd in COMMANDS
        if cmd.help_group == group and (cmd.help_key or cmd.key)
    )
    return rows


def help_text() -> str:
    """Task-grouped help shared by `?`, the help screen, and `lpui help`."""
    lines = ["lazyplan — plan journal for you and your agent", ""]
    for group in HELP_GROUPS:
        rows = _help_rows(group)
        if not rows:
            continue
        lines.append(group)
        for key, hint in rows:
            lines.append(f"  {key:<{_HELP_WIDTH}} {hint}")
        lines.append("")
    lines.append("  lpui help".ljust(_HELP_WIDTH + 2) + " same help at the shell")
    return "\n".join(lines).rstrip()


def hint_bar(width: int | None = None) -> str:
    """One-line key hints; drops the least important items on narrow screens."""
    items = list(HINT_ITEMS)
    text = " · ".join(f"{key} {label}" for key, label in items)
    for key in ("c", "d", "x"):
        if width is None or len(text) <= width:
            break
        items = [item for item in items if item[0] != key]
        text = " · ".join(f"{key_} {label}" for key_, label in items)
    return text


HELP_TEXT = help_text()
KEYMAP = keymap()
