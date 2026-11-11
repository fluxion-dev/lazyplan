"""AGENTS.md and .gitignore snippet management."""

from __future__ import annotations

from pathlib import Path

from . import textfile
from .data_text import data_text

AGENTS_MARK_BEGIN = "<!-- lazyplan:start -->"
AGENTS_MARK_END = "<!-- lazyplan:end -->"


def render_home_agents_snippet(db: Path) -> str:
    """AGENTS.md section for home placement; never claims a repo database."""
    body = f"""## lazyplan (`lpui`)

Plan of record: `{db}` (shared home). Human watches `lpui ui`; agents work
through the CLI with `--actor <name>`.

- Start a session with `lpui --porcelain next`: it claims the first todo. Use
  `lpui --porcelain brief` when you need the whole active picture.
- Use `--porcelain` in the active loop: one tab-separated row per record with
  no glyphs; `--json` wins when you need full fidelity.
- Renew the lease while you work (`claim renew`), note handoffs, and release it
  when you stop. Block parked work with `task block --reason`.
- Move the task doing before code; after each commit, link it with
  `lpui --porcelain link --kind task --id T` (or `lpui task finish`), then move it on.
- Run `lpui --porcelain audit --since 7.days` before closing a plan, and mark
  criteria done only after recording evidence.
- Lifecycle hooks keep each top-level host session's heartbeat current; they
  never move work.
"""
    return body


def ensure_agents_md(repo_root: Path, body: str | None = None) -> tuple[bool, str]:
    """Append the lazyplan section to repo AGENTS.md if missing. Idempotent."""
    dest = repo_root / "AGENTS.md"
    snippet = f"{AGENTS_MARK_BEGIN}\n{body or data_text('AGENTS.md')}{AGENTS_MARK_END}\n"
    wanted = (body or data_text("AGENTS.md")).strip()
    if dest.is_file():
        text = textfile.read(dest)
        if AGENTS_MARK_BEGIN in text and wanted in text:
            return False, "up-to-date"
        if AGENTS_MARK_BEGIN in text:
            # stale snippet: replace the marked block
            before, _, rest = text.partition(AGENTS_MARK_BEGIN)
            _, _, after = rest.partition(AGENTS_MARK_END)
            textfile.write(dest, before.rstrip() + "\n\n" + snippet + after.lstrip())
            return True, "updated"
        textfile.write(dest, text.rstrip() + "\n\n" + snippet)
        return True, "appended"
    textfile.write(dest, "# Agent instructions\n\n" + snippet)
    return True, "created"


def remove_agents_md(repo_root: Path) -> tuple[bool, str]:
    """Strip only the marked lazyplan block; keep the rest of AGENTS.md."""
    dest = repo_root / "AGENTS.md"
    try:
        text = textfile.read(dest)
    except OSError:
        return False, "absent"
    if AGENTS_MARK_BEGIN not in text:
        return False, "absent"
    before, _, rest = text.partition(AGENTS_MARK_BEGIN)
    _, _, after = rest.partition(AGENTS_MARK_END)
    cleaned = before.rstrip() + "\n\n" + after.lstrip()
    if cleaned.strip() in ("", "# Agent instructions"):
        dest.unlink()
    else:
        textfile.write(dest, cleaned.rstrip() + "\n")
    return True, "removed"


def append_gitignore(root: Path, entry: str) -> bool:
    """Append entry to the repo .gitignore when missing. Returns True when added."""
    entry = entry.strip()
    if not entry:
        return False
    gi = Path(root).expanduser() / ".gitignore"
    try:
        raw = textfile.read(gi) if gi.is_file() else ""
    except OSError:
        return False
    lines = [ln.strip().rstrip("/") for ln in raw.splitlines()]
    if entry.rstrip("/") in lines:
        return False
    try:
        textfile.append(gi, ("\n" if raw and not raw.endswith("\n") else "") + entry + "\n")
    except OSError:
        return False
    return True
