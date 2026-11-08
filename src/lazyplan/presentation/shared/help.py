"""Help text and key hints derived from the canonical registry."""

from __future__ import annotations

from .registry import COMMANDS, key_deprecations

NAV_ROWS: tuple[tuple[str, str], ...] = (
    ("j/k, up/down, click", "move cursor / select"),
    ("left/right, click arrow", "fold / unfold row"),
    ("[ / ]", "history back / forward"),
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
    ("f", "mode"),
    ("g", "source"),
    ("?", "help"),
    ("c", "commands"),
    ("O", "override"),
)

HELP_GROUPS: tuple[str, ...] = ("MOVE", "FIND", "APP", "CHANGE", "TRUST")
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
    for cmd in COMMANDS:
        if cmd.help_group != group:
            continue
        key = cmd.help_key or cmd.key
        if not key and group != "TRUST":
            continue
        rows.append((key or "c", cmd.help_hint or cmd.label.lower()))
    return rows


def help_text() -> str:
    """Task-grouped help shared by `?`, the help screen, and `lpui help`."""
    lines = ["lazyplan — plan journal for you and your agent", ""]
    current_mode = ""
    for group in HELP_GROUPS:
        rows = _help_rows(group)
        if not rows:
            continue
        mode = "OVERRIDE" if group in ("CHANGE", "TRUST") else "OBSERVE"
        if mode != current_mode:
            lines.append(mode)
            current_mode = mode
        lines.append(group)
        for key, hint in rows:
            lines.append(f"  {key:<{_HELP_WIDTH}} {hint}")
        lines.append("")
    lines.append("  lpui help".ljust(_HELP_WIDTH + 2) + " same help at the shell")
    keys = key_deprecations()
    if keys:
        lines.extend(["", "DEPRECATED"])
        for dep in keys:
            lines.append(
                f"  {dep.name:<{_HELP_WIDTH}} {dep.replacement} (removed in {dep.removal})"
            )
    return "\n".join(lines).rstrip()


def hint_bar(width: int | None = None, markup: bool = False) -> str:
    """One-line key hints; drops the least important items on narrow screens."""
    items = list(HINT_ITEMS)
    text = " · ".join(f"{key} {label}" for key, label in items)
    for key in ("c", "d", "g", "x"):
        if width is None or len(text) <= width:
            break
        items = [item for item in items if item[0] != key]
        text = " · ".join(f"{key_} {label}" for key_, label in items)
    if markup:
        return " · ".join(f"[reverse] {key} [/]{label}" for key, label in items)
    return text


HELP_TEXT = help_text()
KEYMAP = keymap()
