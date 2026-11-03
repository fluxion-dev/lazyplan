"""Shared Markdown export: destination rules, overwrite protection, and writes."""

from __future__ import annotations

from pathlib import Path

from ...infrastructure import textfile
from ...infrastructure.paths import download_dir


class ExportError(Exception):
    """A destination cannot be used for a Markdown export."""


def default_export_path(plan_id: int, *, default_dir: Path | None = None) -> Path:
    """Return the default ``plan-P<id>.md`` path for one plan."""
    folder = default_dir or download_dir() or Path.cwd()
    return folder / f"plan-P{plan_id}.md"


def resolve_export_path(
    raw: str | Path | None,
    plan_id: int,
    *,
    default_dir: Path | None = None,
) -> Path:
    """Resolve a user-supplied path, adding the default filename or ``.md``."""
    if raw is None or not str(raw).strip():
        return default_export_path(plan_id, default_dir=default_dir).resolve()
    path = Path(raw).expanduser()
    if path.is_dir():
        path = path / default_export_path(plan_id, default_dir=default_dir).name
    elif not path.suffix:
        path = path.with_suffix(".md")
    return path.resolve()


def display_path(path: Path) -> str:
    """Return *path* with the current home directory shortened to ``~``."""
    try:
        relative = path.relative_to(Path.home())
    except ValueError:
        return str(path)
    return "~" if not relative.parts else f"~/{relative.as_posix()}"


def write_export(path: Path, text: str, *, force: bool = False) -> Path:
    """Create parents and atomically write *text*, respecting overwrite rules."""
    target = Path(path).expanduser()
    shown = display_path(target)
    if target.exists() and not target.is_file():
        raise ExportError(f"{shown} is not a file")
    if target.exists() and not force:
        raise ExportError(f"{shown} already exists; choose overwrite to replace it")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        textfile.write_atomic(target, text)
    except OSError as exc:
        raise ExportError(f"could not export {shown}: {exc}") from exc
    return target.resolve()
