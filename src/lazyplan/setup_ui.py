"""Setup wizard rendering: banner, steps, review, prompts, and success.

No setup decisions live here. Every function takes a writer/reader so the
wizard is testable and `--json` paths can skip it entirely.
"""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from .design import ANSI, ASCII_ICONS, ICONS
from .skills import AgentHost

Progress = Callable[[str], object]


def color_enabled(stream: TextIO, json_mode: bool = False) -> bool:
    """ANSI only on an interactive stream with color explicitly allowed."""
    if json_mode or os.environ.get("NO_COLOR") or os.environ.get("LAZYPLAN_NO_COLOR"):
        return False
    if os.environ.get("CLICOLOR", "") == "0":
        return False
    if os.environ.get("TERM", "") == "dumb":
        return False
    try:
        return stream.isatty()
    except (AttributeError, ValueError):
        return False


def _paint(text: str, *codes: str, color: bool) -> str:
    if not color:
        return text
    prefix = "".join(ANSI[c] for c in codes if c in ANSI)
    return f"{prefix}{text}{ANSI['reset']}"


def _icon(name: str, color: bool) -> str:
    return ICONS[name] if color else ASCII_ICONS[name]


def _line(write: Progress, text: str = "") -> None:
    """Write one full line; callers pass a raw stream write function."""
    write(text + "\n")


def _ask(write: TextIO, read: Callable[[], str], prompt: str) -> str:
    write.write(prompt)
    write.flush()
    return read() or ""


def terminal_width() -> int:
    try:
        return max(40, min(shutil.get_terminal_size((80, 24)).columns, 80))
    except OSError:
        return 80


def wrap(text: str, indent: str = "  ", width: int | None = None) -> list[str]:
    """Word-wrap to the terminal width, keeping the indent on every line."""
    import textwrap

    width = width or terminal_width()
    body = textwrap.wrap(text, width=max(20, width - len(indent))) or [""]
    return [indent + line for line in body]


def banner(write: TextIO, color: bool, version: str = "") -> None:
    title = _paint("lazyplan setup", "bold", "cyan", color=color)
    mark = _paint(_icon("setup", color), "cyan", color=color)
    suffix = f"  {_paint('v' + version, 'dim', color=color)}" if version else ""
    _line(write.write, f"{mark} {title}{suffix}")
    _line(
        write.write,
        _paint(
            "  Choose where plans live, which agents get the skill, and their read-only plugins.",
            "dim",
            color=color,
        ),
    )
    _line(write.write)


def step(write: TextIO, index: int, total: int, title: str, color: bool) -> None:
    _line(
        write.write,
        f"{_paint(f'{index}/{total}', 'dim', color=color)} {_paint(title, 'bold', color=color)}",
    )


def placement_choices(repo_root: Path | None, home: Path) -> list[tuple[str, str, Path, str]]:
    """(key, label, path, tradeoff) for the placement question."""
    from .repo import repo_plan_db_path, shared_db_path

    choices = [
        (
            "home",
            "Home",
            shared_db_path(home),
            "Plans follow you across every repo. Nothing is written into this checkout.",
        )
    ]
    if repo_root is not None:
        choices.append(
            (
                "repo",
                "This repo",
                repo_plan_db_path(repo_root),
                "Share with teammates. Config and templates are committed; the database is ignored.",
            )
        )
    return choices


def render_placement(
    write: TextIO,
    repo_root: Path | None,
    home: Path,
    current: str,
    color: bool,
) -> None:
    for number, (key, label, path, note) in enumerate(placement_choices(repo_root, home), 1):
        mark = _icon("check" if key == current else "circle", color)
        name = _paint(label, "bold", "white" if key == current else "dim", color=color)
        _line(write.write, f"  {number} {mark} {name}  {path}")
        for line in wrap(note, "       ", terminal_width()):
            _line(write.write, _paint(line, "dim", color=color))


def ask_placement(
    write: TextIO,
    read: Callable[[], str],
    repo_root: Path | None,
    home: Path,
    current: str,
    color: bool,
) -> str:
    """Ask for home or repo; empty input keeps the current choice."""
    keys = [key for key, _label, _path, _note in placement_choices(repo_root, home)]
    step(write, 1, 3, "Where plans live", color)
    render_placement(write, repo_root, home, current, color)
    answer = _ask(write, read, f"  choose [{'/'.join(keys)}] ({current}): ").strip().lower()
    if answer.isdigit():
        index = int(answer) - 1
        if 0 <= index < len(keys):
            return keys[index]
    if answer in keys:
        return answer
    return current


def render_agents(
    write: TextIO,
    hosts: list[AgentHost],
    selected: list[str],
    color: bool,
) -> None:
    for number, host in enumerate(hosts, 1):
        picked = host.key in selected
        mark = _icon("check" if picked else "circle", color)
        name = _paint(host.label, "bold" if picked else "dim", color=color)
        state = "detected" if host.detected else "not detected"
        state_color = "green" if host.detected else "dim"
        _line(
            write.write,
            f"  {number} {mark} {name}  {_paint(state, state_color, color=color)}  "
            f"{_paint(host.hint, 'dim', color=color)}",
        )


def ask_agents(
    write: TextIO,
    read: Callable[[], str],
    hosts: list[AgentHost],
    selected: list[str],
    color: bool,
) -> list[str]:
    """Ask which agents get the skill; accepts numbers, keys, all, or none."""
    from .skills import parse_tool_selection

    detected = [host.key for host in hosts if host.detected]
    default = selected or detected or [host.key for host in hosts[:1]]
    step(write, 2, 3, "Your agents", color)
    render_agents(write, hosts, default, color)
    _line(
        write.write,
        _paint(
            "  pick numbers or names, 'all', or 'none'. Empty keeps the marked set.",
            "dim",
            color=color,
        ),
    )
    answer = _ask(write, read, "  toggle [numbers/all/none] (detected): ").strip()
    if not answer:
        return default
    if answer.lower() == "none":
        return []
    return parse_tool_selection(answer, hosts)


def render_review(
    write: TextIO,
    db: Path,
    templates: Path,
    skills: list[Path],
    state_path: Path,
    config: Path | None,
    color: bool,
    plugins: list[tuple[str, Path]] | None = None,
) -> None:
    step(write, 3, 3, "Review", color)
    rows = [("database", str(db)), ("templates", str(templates))]
    if config is not None:
        rows.append(("config", str(config)))
    for label, value in rows:
        _line(write.write, f"  {_paint(label.ljust(10), 'bold', color=color)} {value}")
    if skills:
        for index, skill in enumerate(skills):
            label = "skills" if index == 0 else ""
            _line(write.write, f"  {_paint(label.ljust(10), 'bold', color=color)} {skill}")
    else:
        _line(write.write, f"  {_paint('skills'.ljust(10), 'bold', color=color)} none")
    if plugins:
        for index, (host, path) in enumerate(plugins):
            label = "plugins" if index == 0 else ""
            _line(
                write.write,
                f"  {_paint(label.ljust(10), 'bold', color=color)} {host}  {path}",
            )
    else:
        _line(write.write, f"  {_paint('plugins'.ljust(10), 'bold', color=color)} none")
    _line(write.write, f"  {_paint('state'.ljust(10), 'bold', color=color)} {state_path}")
    _line(write.write)


def confirm(write: TextIO, read: Callable[[], str], color: bool) -> bool:
    """Y/n review confirmation; empty means yes."""
    answer = _ask(write, read, "  install these resources? [Y/n]: ").strip().lower()
    if answer in ("n", "no"):
        return False
    return True


def success(
    write: TextIO,
    db: Path,
    skills: list[Path],
    backups: list[Path],
    color: bool,
    plugins: list[Path] | None = None,
) -> None:
    mark = _paint(_icon("check", color), "green", color=color)
    _line(write.write, f"{mark} {_paint('Setup complete', 'bold', 'green', color=color)}")
    _line(write.write, f"  {_paint('database', 'bold', color=color)} {db}")
    for skill in skills:
        _line(write.write, f"  {_paint('skill', 'bold', color=color)}    {skill}")
    for plugin in plugins or []:
        _line(write.write, f"  {_paint('plugin', 'bold', color=color)}   {plugin}")
    for backup in backups:
        _line(
            write.write,
            f"  {_paint('backup', 'bold', color=color)}   {backup}",
        )
    _line(write.write, f"  {_paint('next', 'bold', color=color)}     {_icon('arrow', color)} lpui")
    _line(write.write)


def note(write: TextIO, text: str, color: bool, level: str = "info") -> None:
    mark = _paint(_icon("warn" if level == "warn" else "dot", color), level, color=color)
    _line(write.write, f"{mark} {text}")


def ask_migration(
    write: TextIO,
    read: Callable[[], str],
    path: Path,
    state: str,
    home_db: Path,
    color: bool,
) -> str:
    """Move/keep/never for an untracked repo database. Defaults to keep."""
    mark = _paint(_icon("warn", color), "yellow", color=color)
    _line(
        write.write,
        f"{mark} {_paint('A repo database is not shared or tracked', 'bold', 'yellow', color=color)}",
    )
    _line(write.write, f"  {path}")
    _line(
        write.write,
        _paint(
            f"  git state: {state}. Plans in this checkout only follow you here.",
            "dim",
            color=color,
        ),
    )
    _line(write.write, f"  Move it to {home_db} so plans follow you everywhere?")
    answer = (
        _ask(write, read, "  1 move   2 keep here   3 never ask for this path   [2]: ")
        .strip()
        .lower()
    )
    return {"1": "move", "move": "move", "3": "never", "never": "never"}.get(answer, "keep")


def stdin_tty() -> bool:
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False
