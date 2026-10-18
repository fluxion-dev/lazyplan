"""Agent-skill installer for `lp init`.

One universal skill covers every modern agent host: OpenCode, Claude Code,
Codex, Gemini CLI, and Cursor all discover skills under `.agents/skills/`
(project) and `~/.agents/skills/` (global). A Claude-native copy under
`.claude/skills/` is written alongside whenever Claude Code is detected, for
older Claude versions that only read their own directory.

Stdlib only. All wizard I/O goes to stderr/stdin so stdout stays pure JSON.
"""

from __future__ import annotations

import os
import shutil
from argparse import Namespace
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from .design import (
    INIT_SKILLS_COMMIT_TIP,
    INIT_SKILLS_COVERAGE,
    INIT_SKILLS_DONE,
    INIT_SKILLS_EXPLAIN,
    INIT_SKILLS_TITLE,
)

SKILL_NAME = "lazyplan"

AGENTS_DIR = ".agents"
SKILLS_DIR = "skills"
CLAUDE_DIR = ".claude"

AGENTS_MARK_BEGIN = "<!-- lazyplan:start -->"
AGENTS_MARK_END = "<!-- lazyplan:end -->"

SKILL_FRONTMATTER = """---
name: lazyplan
description: Plan and track work with lazyplan (lp) — projects, stories, tasks, proposals. Use when the user asks to plan work, track progress, break down a feature, check status, or when repo instructions mention `lp`.
license: MIT
compatibility: opencode, claude-code, codex, gemini-cli, cursor
---
"""

SKILL_BODY = """# lazyplan (`lp`) — repo issue tracker

`lp` is the repo's plan of record: projects > stories > tasks, stored in
`.plan/lazyplan.db` (SQLite, committed with the repo or local — check
`.plan/config.json`). The human watches `lp ui`; agents inject work through
the CLI. Never touch the TUI process — only call `lp`.

## Identity

Pass `--actor <name>` on every write so the human sees who did what in
`lp feed` (e.g. `lp --actor opencode add-task ...`). Reads don't need it.
`--actor` and `--json` work before or after the verb
(`lp list --json` == `lp --json list`).

## DB scoping (first match wins)

`--db PATH` → `$LAZYPLAN_DB` → enclosing git repo's `.plan/lazyplan.db` →
global `~/.local/share/lazyplan/lazyplan.db`. Running from any subdirectory
of the repo resolves to that repo's DB. Don't override `--db` unless asked.

## Read first

```bash
lp list [--status todo|doing|done] [--project ID] [--owner NAME]  # tree
lp show --kind project|story|task --id N                          # full context
lp gantt [--tasks] [--width 40]                                   # timeline
lp feed --limit 20                                                # recent activity
lp export --format json                                           # full dump when you need everything
lp info                                                           # resolved db path + counts (scope debugging)
```

Add `--json` for machine-parseable output (`lp list --json`).

## Write: full CRUD

Every entity supports create → read (`show`) → update/status → delete.
`--kind` is project|story|task everywhere it appears.

```bash
lp --actor NAME add-project --name "API v2" [--goal .. --metrics .. --scope-in .. --scope-out ..]
lp --actor NAME add-story --project P --title "Feature Y" [--owner me --priority p0 --estimate 2w]
lp --actor NAME add-task --story S --title "Do X" [--desc ctx --owner me --priority p1 --estimate 2d]
lp --actor NAME update --kind task --id T [--title .. --desc .. --owner .. --priority p0|none --estimate ..]
lp --actor NAME status --kind task --id T --to doing|done
lp --actor NAME delete --kind task --id T                         # immediate, no confirm
```

Deleting a project removes its stories and tasks — double-check ids first.
Closing with open acceptance criteria warns but never blocks.

## Checklists, links, risks, milestones

```bash
lp --actor NAME add-criteria --kind task --id T --text "Works offline"  # acceptance item
lp criteria --kind task --id T                                          # list items
lp check --id C / lp uncheck --id C                                     # tick/untick (advisory)
lp --actor NAME delete-criteria --id C
lp --actor NAME add-link --kind task --id T --url URL [--label spec]    # attach reference
lp links --kind task --id T                                             # list links
lp --actor NAME delete-link --id L
lp --actor NAME add-risk --project P --title "Slip" [--likelihood high --impact high --mitigation buf]
lp risks --project P                                                    # likelihood x impact first
lp --actor NAME risk-status --id R --to mitigated
lp --actor NAME add-milestone --project P --title "Beta" --date 2026-11-15
lp milestones --project P                                               # list markers
lp --actor NAME delete-milestone --id M
lp --actor NAME import --file dump.json                                 # load an export dump (remaps ids)
```

## Human-in-the-loop (preferred for judgment calls)

```bash
lp --actor NAME propose --kind task --parent S --title "Refactor X"  # parent: story id for tasks, project id for stories
lp --actor NAME ask --question "Which scope: minimal or full?"       # human answers in UI
lp questions --all          # check for answers (poll; agents: lp feed --json --follow &)
lp proposals --status pending
```

Propose/ask instead of guessing when scope, taste, or repo-wide impact is
involved. The human approves (`4` then `a`/`x` in `lp ui`). Never
`approve`/`reject` your own proposals or `answer` your own questions —
those verbs belong to the human in the UI.

## Rules

- One DB write = one feed event; keep titles imperative and scoped.
- Prefer update/status over delete + recreate (ids and history survive).
- Never invent project/story ids: `lp list` to discover them.
- Never `lp seed` a real repo plan — it inserts demo data.
- Full verb reference: `lp --help` (CLI == TUI `:` command bar).
"""

AGENTS_SNIPPET = """## lazyplan (`lp`)

Repo plan of record: projects > stories > tasks in `.plan/lazyplan.db`.
Human watches `lp ui`; agents work via the CLI with `--actor <name>`.

- Read: `lp list`, `lp show --kind story --id N`, `lp feed --limit 20` (`--json` for parsing)
- Write (full CRUD): `lp add-project`, `lp add-story`, `lp add-task`, `lp update`, `lp status`, `lp delete` (all with `--actor <name>`)
- Extras: `lp add-criteria`, `lp add-link`, `lp add-risk`, `lp add-milestone` (flags in the skill)
- Unsure? `lp propose` / `lp ask` for human approval
- Full skill: `.agents/skills/lazyplan/SKILL.md` · verbs: `lp --help`
"""


@dataclass(frozen=True)
class AgentHost:
    """One agent host the wizard reports on."""

    key: str
    label: str
    detected: bool
    hint: str


@dataclass
class InstallResult:
    """Outcome of a skill install, serialized into `lp init` JSON."""

    scope: str
    installed: list[str] = field(default_factory=list)
    updated_agents_md: str | None = None
    skipped: str | None = None

    def to_dict(self) -> dict:
        """JSON-safe payload."""
        return {
            "scope": self.scope,
            "installed": list(self.installed),
            "agents_md": self.updated_agents_md,
            "skipped": self.skipped,
        }


def render_skill() -> str:
    """Full SKILL.md text for the lazyplan skill."""
    return SKILL_FRONTMATTER + SKILL_BODY


def render_agents_snippet() -> str:
    """AGENTS.md section, wrapped in idempotent markers."""
    return f"{AGENTS_MARK_BEGIN}\n{AGENTS_SNIPPET}{AGENTS_MARK_END}\n"


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
    """Project when inside a repo, else global."""
    return "project" if repo_root is not None else "global"


def skill_targets(scope: str, repo_root: Path | None, home: Path) -> list[Path]:
    """SKILL.md destinations for a scope (universal + Claude-native when relevant)."""
    targets: list[Path] = []
    if scope in ("project", "both") and repo_root is not None:
        targets.append(repo_root / AGENTS_DIR / SKILLS_DIR / SKILL_NAME / "SKILL.md")
    if scope in ("global", "both"):
        targets.append(home / AGENTS_DIR / SKILLS_DIR / SKILL_NAME / "SKILL.md")
    return targets


def claude_targets(scope: str, repo_root: Path | None, home: Path) -> list[Path]:
    """Claude-native copies for older Claude versions (same content)."""
    targets: list[Path] = []
    if scope in ("project", "both") and repo_root is not None:
        targets.append(repo_root / CLAUDE_DIR / SKILLS_DIR / SKILL_NAME / "SKILL.md")
    if scope in ("global", "both"):
        targets.append(home / CLAUDE_DIR / SKILLS_DIR / SKILL_NAME / "SKILL.md")
    return targets


def write_skill_file(dest: Path) -> tuple[bool, str]:
    """Write SKILL.md; returns (changed, status string)."""
    content = render_skill()
    if dest.is_file() and dest.read_text() == content:
        return False, "up-to-date"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content)
    return True, "wrote"


def ensure_agents_md(repo_root: Path) -> tuple[bool, str]:
    """Append the lazyplan section to repo AGENTS.md if missing. Idempotent."""
    dest = repo_root / "AGENTS.md"
    snippet = render_agents_snippet()
    if dest.is_file():
        text = dest.read_text()
        if AGENTS_MARK_BEGIN in text and AGENTS_SNIPPET.strip() in text:
            return False, "up-to-date"
        if AGENTS_MARK_BEGIN in text:
            # stale snippet: replace the marked block
            before, _, rest = text.partition(AGENTS_MARK_BEGIN)
            _, _, after = rest.partition(AGENTS_MARK_END)
            dest.write_text(before.rstrip() + "\n\n" + snippet + after.lstrip())
            return True, "updated"
        dest.write_text(text.rstrip() + "\n\n" + snippet)
        return True, "appended"
    dest.write_text("# Agent instructions\n\n" + snippet)
    return True, "created"


def install(
    scope: str,
    repo_root: Path | None,
    home: Path | None = None,
    with_claude_copy: bool = False,
    with_agents_md: bool = True,
) -> InstallResult:
    """Non-interactive install to a scope. Never prompts, never raises on write."""
    home = home or Path.home()
    if scope == "none":
        return InstallResult(scope=scope, skipped="user skipped skill setup")
    if scope in ("project", "both") and repo_root is None:
        # No repo to write project files into: fall back to global only.
        scope = "global"
    result = InstallResult(scope=scope)
    for dest in skill_targets(scope, repo_root, home):
        _, status = write_skill_file(dest)
        result.installed.append(f"{dest} ({status})")
    if with_claude_copy:
        for dest in claude_targets(scope, repo_root, home):
            _, status = write_skill_file(dest)
            result.installed.append(f"{dest} ({status})")
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
    except (EOFError, KeyboardInterrupt):
        return default
    if valid is not None and line and line not in valid:
        print(f"  pick one of {sorted(valid)} — using default [{default}]", file=out)
        return default
    return line or default


def run_wizard(
    repo_root: Path | None,
    home: Path | None = None,
    read: Callable[[], str] | None = None,
    write: TextIO | None = None,
) -> InstallResult:
    """Interactive `lp init` wizard. All I/O on stderr/stdin; stdout stays JSON."""
    import sys

    home = home or Path.home()
    out: TextIO = write if write is not None else sys.stderr
    hosts = detect_agents(home)
    found = [h for h in hosts if h.detected]

    print(f"\n{INIT_SKILLS_TITLE}", file=out)
    print(INIT_SKILLS_EXPLAIN, file=out)
    if found:
        print("Detected on this machine:", file=out)
        for h in found:
            print(f"  [x] {h.label} ({h.hint})", file=out)
        missing = [h.label for h in hosts if not h.detected]
        if missing:
            print(f"Not found (still covered): {', '.join(missing)}", file=out)
    else:
        print(
            "No agent CLIs detected — the universal skill still works when you install one.",
            file=out,
        )
    print(INIT_SKILLS_COVERAGE, file=out)

    dflt = default_scope(repo_root)
    print("", file=out)
    print("Where should the skill live?", file=out)
    if repo_root is not None:
        print(
            f"  1) Project  {repo_root}/.agents/skills/lazyplan/  (commit it — team shares it)",
            file=out,
        )
    else:
        print("  1) Project  (unavailable — not inside a git repo)", file=out)
    print(f"  2) Global   {home}/.agents/skills/lazyplan/  (all your repos)", file=out)
    print("  3) Both     (project + global)", file=out)
    print("  4) Skip     (DB only, no skill files)", file=out)
    dflt_num = {"project": "1", "global": "2", "both": "3"}[dflt]
    choice = _prompt(
        f"Pick [1/2/3/4] (default {dflt_num}): ",
        valid={"1", "2", "3", "4"},
        default=dflt_num,
        read=read,
        write=out,
    )
    scope = {"1": "project", "2": "global", "3": "both", "4": "none"}[choice]
    if scope == "none":
        print("Skipped skill setup — DB is ready.", file=out)
        return InstallResult(scope=scope, skipped="user skipped skill setup")
    if scope == "project" and repo_root is None:
        print("Not in a repo — installing globally instead.", file=out)
        scope = "global"

    with_claude = any(h.key == "claude" and h.detected for h in hosts)
    if with_claude:
        print("Claude Code detected — also writing the `.claude/skills/` copy.", file=out)

    with_md = False
    if scope in ("project", "both") and repo_root is not None:
        ans = _prompt(
            "Add the `## lazyplan` pointer to repo AGENTS.md? [Y/n]: ",
            valid={"y", "n", "Y", "N", ""},
            default="Y",
            read=read,
            write=out,
        )
        with_md = ans.lower() != "n"

    result = install(scope, repo_root, home, with_claude_copy=with_claude, with_agents_md=with_md)
    for line in result.installed:
        print(f"  skill: {line}", file=out)
    if result.updated_agents_md:
        print(f"  agents-md: {result.updated_agents_md}", file=out)
    print(INIT_SKILLS_DONE, file=out)
    if scope in ("project", "both"):
        print(INIT_SKILLS_COMMIT_TIP, file=out)
    _ = sys  # keep import local to this function
    return result


def should_prompt(args: Namespace, is_tty: bool) -> bool:
    """True only for an interactive human `lp init` with no scope overrides."""
    no_skills = bool(getattr(args, "no_skills", False))
    scope_arg = str(getattr(args, "skills_scope", "") or "").strip()
    yes = bool(getattr(args, "yes", False))
    as_json = bool(getattr(args, "json", False))
    if no_skills or scope_arg or yes or as_json or not is_tty:
        return False
    return True


def handle_init(args: Namespace, repo_root: Path | None, home: Path | None = None) -> dict:
    """Decide interactive vs non-interactive skill setup for `lp init`."""
    import sys

    home = home or Path.home()
    no_skills = bool(getattr(args, "no_skills", False))
    scope_arg = str(getattr(args, "skills_scope", "") or "").strip()
    yes = bool(getattr(args, "yes", False))
    if no_skills or scope_arg == "none":
        return InstallResult(scope="none", skipped="--no-skills").to_dict()
    if scope_arg in ("project", "global", "both"):
        hosts = detect_agents(home)
        with_claude = any(h.key == "claude" and h.detected for h in hosts)
        res = install(scope_arg, repo_root, home, with_claude_copy=with_claude)
        return res.to_dict()
    if yes:
        hosts = detect_agents(home)
        with_claude = any(h.key == "claude" and h.detected for h in hosts)
        res = install(default_scope(repo_root), repo_root, home, with_claude_copy=with_claude)
        return res.to_dict()
    is_tty = bool(sys.stdin.isatty() and sys.stdout.isatty())
    if should_prompt(args, is_tty):
        try:
            return run_wizard(repo_root, home).to_dict()
        except (EOFError, KeyboardInterrupt, OSError):
            return InstallResult(scope="none", skipped="non-interactive").to_dict()
    reason = "--json (machine output)" if bool(getattr(args, "json", False)) else "non-interactive"
    if os.environ.get("LAZYPLAN_NO_SKILLS", "").strip():
        reason = "$LAZYPLAN_NO_SKILLS"
    return InstallResult(scope="none", skipped=reason).to_dict()
