"""Agent-skill installer for first-run setup.

One universal skill covers every modern agent host: OpenCode, Claude Code,
Codex, Gemini CLI, and Cursor all discover skills under `.agents/skills/`
(plan) and `~/.agents/skills/` (global). A Claude-native copy under
`.claude/skills/` is written alongside whenever Claude Code is detected, for
older Claude versions that only read their own directory.

Stdlib only. All wizard I/O goes to stderr/stdin so stdout stays pure JSON.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from . import textfile


def _data_text(name: str) -> str:
    """Read one packaged agent-facing Markdown file."""
    from importlib.resources import files

    return (files("lazyplan") / "data" / name).read_text(encoding="utf-8")


_SKILL_TEXT = _data_text("SKILL.md")
SKILL_BODY = _SKILL_TEXT.split("---", 2)[2].lstrip("\n")
AGENTS_SNIPPET = _data_text("AGENTS.md")

SKILL_NAME = "lazyplan"

__all__ = [
    "AGENTS_SNIPPET",
    "SKILL_BODY",
    "render_skill",
    "render_home_agents_snippet",
]

AGENTS_DIR = ".agents"
SKILLS_DIR = "skills"

AGENTS_MARK_BEGIN = "<!-- lazyplan:start -->"
AGENTS_MARK_END = "<!-- lazyplan:end -->"


@dataclass(frozen=True)
class AgentHost:
    """One agent host the wizard reports on."""

    key: str
    label: str
    detected: bool
    hint: str


@dataclass
class InstallResult:
    """Outcome of a skill install, serialized into setup JSON."""

    scope: str
    installed: list[str] = field(default_factory=list)
    updated_agents_md: str | None = None
    skipped: str | None = None
    templates: dict | None = None

    def to_dict(self) -> dict:
        """JSON-safe payload."""
        payload: dict[str, object] = {
            "scope": self.scope,
            "installed": list(self.installed),
            "agents_md": self.updated_agents_md,
            "skipped": self.skipped,
        }
        if self.templates is not None:
            payload["templates"] = self.templates
        return payload


@dataclass
class SkillPlan:
    """Where setup intends to put skill files and the AGENTS.md pointer."""

    scope: str
    tools: list[str] | None
    skills_dir: str | None
    skill_files: list[Path]
    agents_md: Path | None
    skipped: str | None = None

    def to_dict(self) -> dict:
        """JSON-safe payload."""
        return {
            "scope": self.scope,
            "tools": list(self.tools or []),
            "skills_dir": self.skills_dir,
            "skill_files": [str(path) for path in self.skill_files],
            "agents_md": str(self.agents_md) if self.agents_md else None,
            "skipped": self.skipped,
        }


def skill_destinations(
    scope: str,
    repo_root: Path | None,
    home: Path,
    tools: list[str] | None,
    skills_dir: str | Path | None = None,
) -> list[Path]:
    """Pure prediction of the SKILL.md files an install would write."""
    if scope == "none":
        return []
    if skills_dir is not None:
        return [Path(skills_dir).expanduser() / SKILL_NAME / "SKILL.md"]
    targets: list[Path] = []
    if scope in ("project", "both") and repo_root is not None:
        targets.extend(skill_targets("project", repo_root, home))
        for tool in tools or []:
            targets.extend(tool_skill_targets(tool, "project", repo_root, home))
    if scope in ("global", "both"):
        targets.extend(global_skill_targets(tools, home))
    seen: set[Path] = set()
    out: list[Path] = []
    for target in targets:
        if target not in seen:
            seen.add(target)
            out.append(target)
    return out


def _empty_plan(reason: str) -> SkillPlan:
    return SkillPlan(
        scope="none",
        tools=None,
        skills_dir=None,
        skill_files=[],
        agents_md=None,
        skipped=reason,
    )


def _plan_for(
    scope: str,
    repo_root: Path | None,
    home: Path,
    tools: list[str] | None,
    skills_dir: str | None,
    *,
    with_agents_md: bool = True,
) -> SkillPlan:
    if scope in ("project", "both") and repo_root is None and skills_dir is None:
        if scope == "project":
            return _empty_plan("project scope needs a git repository")
        scope = "global"
    return SkillPlan(
        scope=scope,
        tools=tools,
        skills_dir=skills_dir,
        skill_files=skill_destinations(scope, repo_root, home, tools, skills_dir),
        agents_md=(
            repo_root / "AGENTS.md"
            if with_agents_md and scope in ("project", "both") and repo_root is not None
            else None
        ),
    )


def plan_choice(
    choice: object,
    repo_root: Path | None,
    home: Path | None = None,
) -> SkillPlan:
    """Resolve skill destinations from a SetupChoice (no argparse, no prompts)."""
    home = home or Path.home()
    if os.environ.get("LAZYPLAN_NO_SKILLS", "").strip():
        return _empty_plan("$LAZYPLAN_NO_SKILLS")
    if getattr(choice, "explicit_db", None):
        return _empty_plan("explicit database")
    if bool(getattr(choice, "no_skills", False)):
        return _empty_plan("--no-skills")
    placement = str(getattr(choice, "placement", "home") or "home")
    scope = "project" if placement == "repo" and repo_root is not None else "global"
    tools = getattr(choice, "agents", None) or None
    skills_dir = getattr(choice, "skills_dir", None)
    return _plan_for(scope, repo_root, home, tools, skills_dir)


def apply_skill_plan(
    plan: SkillPlan,
    repo_root: Path | None,
    home: Path | None = None,
) -> InstallResult:
    """Write the files described by a `SkillPlan`."""
    home = home or Path.home()
    if plan.scope == "none":
        return InstallResult(scope=plan.scope, skipped=plan.skipped)
    result = install(
        plan.scope,
        repo_root,
        home,
        with_agents_md=plan.agents_md is not None,
        tools=plan.tools,
        skills_dir=plan.skills_dir,
    )
    for dest_line in list(result.installed):
        dest = dest_line.rsplit(" (", 1)[0]
        try:
            ensure_skill_db(dest)
        except OSError:
            pass
    return result


def render_skill() -> str:
    """Full SKILL.md text for the lazyplan skill."""
    return _SKILL_TEXT


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
- Run `lpui --porcelain audit --since 7.days` before closing a plan, and tick
  criteria only with evidence.
- Lifecycle hooks are read-only; they remind, never move work.
"""
    return body


def detect_agents(home: Path | None = None) -> list[AgentHost]:
    """Detect installed agent hosts via binaries + config dirs (no side effects)."""
    home = home or Path.home()
    specs = (
        ("opencode", "OpenCode", "opencode", home / ".config" / "opencode"),
        ("claude", "Claude Code", "claude", home / ".claude"),
        ("codex", "Codex", "codex", home / ".codex"),
        ("gemini", "Gemini CLI", "gemini", home / ".gemini"),
        ("cursor", "Cursor", "cursor", home / ".cursor"),
        ("copilot", "Copilot CLI", "copilot", home / ".copilot"),
    )
    out = []
    for key, label, binary, cfg in specs:
        found = shutil.which(binary) is not None or cfg.exists()
        hint = f"`{binary}`" if shutil.which(binary) else str(cfg)
        out.append(AgentHost(key=key, label=label, detected=found, hint=hint))
    return out


def default_scope(repo_root: Path | None) -> str:
    """Plan when inside a repo, else global."""
    return "project" if repo_root is not None else "global"


def skill_targets(scope: str, repo_root: Path | None, home: Path) -> list[Path]:
    """SKILL.md destinations for a scope (universal + Claude-native when relevant)."""
    targets: list[Path] = []
    if scope in ("project", "both") and repo_root is not None:
        targets.append(repo_root / AGENTS_DIR / SKILLS_DIR / SKILL_NAME / "SKILL.md")
    if scope in ("global", "both"):
        targets.append(home / AGENTS_DIR / SKILLS_DIR / SKILL_NAME / "SKILL.md")
    return targets


# Native per-tool skill homes: project-relative dir ("" = no project side)
# plus home-relative dir. The open-standard `.agents/skills` location is
# always installed as fallback by skill_targets, never listed here.
TOOL_SKILL_DIRS: dict[str, tuple[str, str]] = {
    "opencode": (".opencode/skills", ".config/opencode/skills"),
    "claude": (".claude/skills", ".claude/skills"),
    "codex": ("", ".codex/skills"),
    "gemini": (".gemini/skills", ".gemini/skills"),
    "cursor": (".cursor/skills", ".cursor/skills"),
}

KNOWN_TOOLS: tuple[str, ...] = ("opencode", "claude", "codex", "gemini", "cursor", "copilot")

# Sibling DB filename kept next to each installed SKILL.md. New installs
# share the ~/.lazyplan home DB; these per-tool paths are legacy one-time
# import sources only (see repo.legacy_db_candidates).
SKILL_DB_NAME = "lazyplan.db"


def skill_db_path(skill_file: str | Path) -> Path:
    """DB sibling for an installed SKILL.md (per agent-skill dir)."""
    return Path(skill_file).expanduser().parent / SKILL_DB_NAME


def agent_local_db_candidates(home: Path | None = None) -> list[Path]:
    """Legacy per-agent DB locations, most-shared first (no side effects).

    Only used as one-time import sources for the shared home DB.
    """
    home = (home or Path.home()).expanduser()
    candidates: list[Path] = [
        home / AGENTS_DIR / SKILLS_DIR / SKILL_NAME / SKILL_DB_NAME,
    ]
    for tool in KNOWN_TOOLS:
        entry = TOOL_SKILL_DIRS.get(tool)
        if entry is None:
            continue
        _, home_dir = entry
        if not home_dir:
            continue
        candidates.append(home / home_dir / SKILL_NAME / SKILL_DB_NAME)
    seen: list[Path] = []
    for cand in candidates:
        if cand not in seen:
            seen.append(cand)
    return seen


def ensure_skill_db(skill_file: str | Path) -> Path:
    """Ensure the sibling DB dir exists; returns the DB path (no schema here)."""
    db = skill_db_path(skill_file)
    db.parent.mkdir(parents=True, exist_ok=True)
    return db


def parse_tool_selection(raw: str, hosts: list[AgentHost]) -> list[str]:
    """Parse wizard tool picking: numbers, keys, 'all', or '' (default)."""
    valid = [h.key for h in hosts if h.key in KNOWN_TOOLS]
    detected = [h.key for h in hosts if h.detected and h.key in KNOWN_TOOLS]
    text = (raw or "").strip().lower()
    if not text:
        return list(detected) if detected else ["opencode"]
    if text in ("all", "*"):
        return list(valid)
    picked: list[str] = []
    for part in text.replace(",", " ").split():
        key: str | None = None
        if part.isdigit():
            idx = int(part) - 1
            if 0 <= idx < len(valid):
                key = valid[idx]
        elif part in valid:
            key = part
        if key is not None and key not in picked:
            picked.append(key)
    return picked if picked else (list(detected) if detected else ["opencode"])


def tool_skill_targets(tool: str, scope: str, repo_root: Path | None, home: Path) -> list[Path]:
    """Native SKILL.md destinations for one tool at a scope.

    Unknown tools and sides with no path yield []. The open-standard
    fallback (skill_targets) is applied separately by the caller.
    """
    entry = TOOL_SKILL_DIRS.get(tool)
    if entry is None:
        return []
    project_dir, home_dir = entry
    targets: list[Path] = []
    if scope in ("project", "both") and repo_root is not None and project_dir:
        targets.append(repo_root / project_dir / SKILL_NAME / "SKILL.md")
    if scope in ("global", "both"):
        targets.append(home / home_dir / SKILL_NAME / "SKILL.md")
    return targets


def global_skill_targets(tools: list[str] | None, home: Path) -> list[Path]:
    """Local install targets: exactly one dir per tool.

    Tools with a known home folder get their canonical dir; tools without
    one (copilot) and the legacy tools=None path share `~/.agents/skills`.
    """
    if tools is None:
        return [home / AGENTS_DIR / SKILLS_DIR / SKILL_NAME / "SKILL.md"]
    targets: list[Path] = []
    for tool in tools:
        entry = TOOL_SKILL_DIRS.get(tool)
        if entry is not None and entry[1]:
            dest = home / entry[1] / SKILL_NAME / "SKILL.md"
        else:
            dest = home / AGENTS_DIR / SKILLS_DIR / SKILL_NAME / "SKILL.md"
        if dest not in targets:
            targets.append(dest)
    return targets


def write_skill_file(dest: Path) -> tuple[bool, str]:
    """Write SKILL.md; returns (changed, status string)."""
    content = render_skill()
    if dest.is_file() and textfile.read(dest) == content:
        return False, "up-to-date"
    dest.parent.mkdir(parents=True, exist_ok=True)
    textfile.write(dest, content)
    return True, "wrote"


def ensure_agents_md(repo_root: Path, body: str | None = None) -> tuple[bool, str]:
    """Append the lazyplan section to repo AGENTS.md if missing. Idempotent."""
    dest = repo_root / "AGENTS.md"
    snippet = f"{AGENTS_MARK_BEGIN}\n{body or _data_text('AGENTS.md')}{AGENTS_MARK_END}\n"
    wanted = (body or _data_text("AGENTS.md")).strip()
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


def _write_skill(seen: set[Path], installed: list[str], dest: Path) -> None:
    """Write one SKILL.md unless already written (dedupes across sides)."""
    if dest in seen:
        return
    seen.add(dest)
    _, status = write_skill_file(dest)
    installed.append(f"{dest} ({status})")


def _install_team_side(
    seen: set[Path],
    installed: list[str],
    repo_root: Path,
    home: Path,
    with_claude_copy: bool,
    tools: list[str] | None,
) -> None:
    """Team side: shared repo standard + native per-tool repo dirs."""
    for dest in skill_targets("project", repo_root, home):
        _write_skill(seen, installed, dest)
    if with_claude_copy:
        for dest in tool_skill_targets("claude", "project", repo_root, home):
            _write_skill(seen, installed, dest)
    for tool in tools or []:
        for dest in tool_skill_targets(tool, "project", repo_root, home):
            _write_skill(seen, installed, dest)


def _install_local_side(
    seen: set[Path],
    installed: list[str],
    repo_root: Path | None,
    home: Path,
    with_claude_copy: bool,
    tools: list[str] | None,
) -> None:
    """Local side: exactly one dir per tool (no universal duplicate)."""
    for dest in global_skill_targets(tools, home):
        _write_skill(seen, installed, dest)
    if with_claude_copy and tools is None:
        for dest in tool_skill_targets("claude", "global", repo_root, home):
            _write_skill(seen, installed, dest)


def install(
    scope: str,
    repo_root: Path | None,
    home: Path | None = None,
    with_claude_copy: bool = False,
    with_agents_md: bool = True,
    tools: list[str] | None = None,
    skills_dir: str | Path | None = None,
) -> InstallResult:
    """Non-interactive install to a scope. Never prompts, never raises on write."""
    home = home or Path.home()
    if scope == "none":
        return InstallResult(scope=scope, skipped="user skipped skill setup")
    if scope in ("project", "both") and repo_root is None:
        # No repo to write plan files into: fall back to global only.
        scope = "global"
    result = InstallResult(scope=scope)
    seen: set[Path] = set()
    if skills_dir is not None:
        _write_skill(
            seen, result.installed, Path(skills_dir).expanduser() / SKILL_NAME / "SKILL.md"
        )
    else:
        if scope in ("project", "both") and repo_root is not None:
            _install_team_side(seen, result.installed, repo_root, home, with_claude_copy, tools)
        if scope in ("global", "both"):
            _install_local_side(seen, result.installed, repo_root, home, with_claude_copy, tools)
    if with_agents_md and scope in ("project", "both") and repo_root is not None:
        _, status = ensure_agents_md(repo_root)
        result.updated_agents_md = f"{repo_root / 'AGENTS.md'} ({status})"
    return result


def _prompt(
    prompt: str,
    valid: set[str] | None = None,
    default: str = "",
    read: Callable[[], str] | None = None,
    write: TextIO | None = None,
) -> str:
    """Prompt on stderr, read stdin; EOF/KeyboardInterrupt means default/skip."""
    import sys

    out: TextIO = write if write is not None else sys.stderr
    print(prompt, file=out, end="", flush=True)
    try:
        line = (read() if read is not None else input()).strip()
    except (EOFError, KeyboardInterrupt, StopIteration):
        return default
    if valid is not None and line and line not in valid:
        print(f"  pick one of {sorted(valid)} — using default [{default}]", file=out)
        return default
    return line or default


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


def prompt_confirm(
    prompt: str,
    default_yes: bool = True,
    read: Callable[[], str] | None = None,
    write: TextIO | None = None,
) -> bool:
    """Y/n prompt on stderr/stdin; EOF/empty means the default. Never raises."""
    default = "Y" if default_yes else "N"
    ans = _prompt(
        f"{prompt} [{'Y/n' if default_yes else 'y/N'}]: ",
        valid={"y", "n", "Y", "N", ""},
        default=default,
        read=read,
        write=write,
    )
    return ans.lower() != "n" if default_yes else ans.lower() == "y"


def _skills_dir_override(args: object) -> str | None:
    """Explicit skill dir: --skills-dir wins, then $LAZYPLAN_SKILLS_DIR."""
    flag = str(getattr(args, "skills_dir", "") or "").strip()
    if flag:
        return flag
    env = os.environ.get("LAZYPLAN_SKILLS_DIR", "").strip()
    return env or None
