"""Agent-skill installer for `lpui init`.

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
description: Plan and track work with lazyplan (lpui) — interview for a project's why/what/acceptance criteria, then cut prioritized stories and tasks. Use when the user asks to plan work, track progress, break down a feature, check status, or when repo instructions mention `lpui`.
license: MIT
compatibility: opencode, claude-code, codex, gemini-cli, cursor
---
"""

SKILL_BODY = """# lazyplan (`lpui`) — local project journal

`lpui` is the repo's plan of record: projects > stories > tasks, stored in
`.plan/lazyplan.db` (SQLite, committed with the repo or local — check
`.plan/config.json`). The human watches `lpui ui`; agents inject work through
the CLI. Never touch the TUI process — only call `lpui`.

A project is: title + priority + why + what + acceptance criteria. Stories cut
a project into slices; tasks cut a story into prioritized units of work. That
is the whole model — no dates, owners, labels, or estimates.

## Identity

Pass `--actor <name>` on every write so the human sees who did what in
`lpui feed` (e.g. `lpui --actor opencode add-task ...`). Reads don't need it.
`--actor` and `--json` work before or after the verb
(`lpui list --json` == `lpui --json list`).

## DB scoping (first match wins)

`--db PATH` → `$LAZYPLAN_DB` → enclosing git repo's `.plan/lazyplan.db` →
global `~/.local/share/lazyplan/lazyplan.db`. Running from any subdirectory
of the repo resolves to that repo's DB. Don't override `--db` unless asked.

## Starting a project: interview first

Never invent a project's definition. When the user asks to plan something,
interview them before writing anything. A solid definition covers:

- Vision: why this exists (one or two sentences) — the problem and the value.
- Scope: explicit in-scope and out-of-scope lists, in plain language. Push
  until both lists are concrete — vague scope is rejected, not recorded.
- Deliverables: tangible outputs and their order.
- Constraints: technical or operational limits, plus assumptions.
- Success metrics: measurable outcomes that mean it worked.
- Acceptance criteria: how we know it is done.
- Quality: ask whether QA testing, refactoring, and documentation cleanup
  steps should be included, and ask what testing is relevant to the changes
  being made. All three are included by default — only an explicit opt-out
  excludes them.

Fold vision into `--why`; scope, deliverables, constraints, and metrics into
`--what`; acceptance criteria become project-level checklist items. There are
no stakeholder, owner, or estimate fields — if it does not fit why, what, or
criteria, it does not belong in the definition.

While interviewing, scout the codebase (explore agents, grep, file reads) so
each question clears up real ambiguity: what exists, what constrains the
approach, what the deliverables touch. Never cut work from an unscouted
definition. Scouting is mandatory before creating anything — project, story,
or task. No row is written from unscouted ground, in any case, no exceptions.
Then record it:

```bash
lpui --actor NAME add-project --title "API v2" --why ".." --what ".." --priority p1
lpui --actor NAME add-criteria --kind project --id P --text "Works offline"
lpui criteria --kind project --id P                                     # list items
lpui check --id C / lpui uncheck --id C                                 # tick/untick (advisory)
```

Only once the definition is agreed, cut the work — stories from the project,
then prioritized tasks from each story, shaped as below plus the default QA,
refactor, and documentation tasks.

Every plan carries QA testing tasks, a refactoring task, and documentation
cleanup by default, shaped by the interview's testing answer. Ground every QA task in the acceptance criteria: each criterion is exercised by a named test task, and DoD checklists reference the criteria they satisfy. Only an explicit user opt-out ("skip QA", "no refactoring") excludes them — silence means include.

Work top priority first. Move rows through todo → doing → done as you go.

## Review gate: plan is truth

Once the definition is recorded and the work is cut, present the plan for check-off before implementing anything:

```bash
lpui list --status all                 # the whole tree
lpui show --kind project --id P        # why/what + criteria + children
```

Walk the human through every story and task, make last edits on the spot, and start executing only on explicit check-off. During execution the plan stays the truth: fold new findings into the plan before changing code, never around it.

## Read first

```bash
lpui list [--status todo|doing|done|all] [--archived] [--project ID] [--priority p0]  # tree (default: all)
lpui show --kind project|story|task --id N                           # full context
lpui feed --limit 20                                                 # recent activity
lpui export --format json                                            # full dump when you need everything
lpui info                                                            # resolved db path + counts (scope debugging)
lpui reconcile                                                       # recompute parent statuses from children
```

Add `--json` for machine-parseable output (`lpui list --json`).

## Write: full CRUD

Every entity supports create → read (`show`) → update/status → delete.
`--kind` is project|story|task everywhere it appears.

```bash
lpui --actor NAME add-project --title "API v2" --why ".." --what ".." --priority p1
lpui --actor NAME add-story --project P --title "Feature Y" [--desc .. --priority p0]
lpui --actor NAME add-task --story S --title "Do X" [--desc ctx --priority p1]
lpui --actor NAME update --kind task --id T [--title .. --desc .. --priority p0|none]
lpui --actor NAME update --kind project --id P [--title .. --what .. --why .. --priority p0|none]
lpui --actor NAME status --kind task --id T --to doing|done
lpui --actor NAME delete --kind task --id T                          # immediate, no confirm
```

Deleting a project removes its stories and tasks — double-check ids first.
Status moves roll parents up automatically: closing the last open task
completes its story and project. Closing with open acceptance criteria warns
but never blocks.

## Acceptance criteria

```bash
lpui --actor NAME add-criteria --kind project --id P --text "Works offline"  # acceptance item
lpui criteria --kind project --id P                                          # list items
lpui check --id C / lpui uncheck --id C                                      # tick/untick (advisory)
lpui --actor NAME delete-criteria --id C
lpui --actor NAME import --file dump.json                                    # load an export dump (remaps ids)
```

Criteria live on projects, stories, and tasks. Project-level criteria are the
definition of done — tick them as the work lands.

## Story standard

Each story states user value in narrative form, with testable criteria:

```bash
lpui --actor NAME add-story --project P --title "Feature Y" --desc "As a [persona], I want [action] so that [benefit]" --priority p1
lpui --actor NAME add-criteria --kind story --id S --text "Given [context], when [action], then [outcome]"
```

Keep stories INVEST: independent, negotiable, valuable, estimable, small,
testable. At creation, `--desc` carries the narrative plus the INVEST check
and the inputs/prerequisites — a story without them is not ready to cut. No
dependency, estimate, or owner fields — sequencing lives in priority order
(work p0 first), context lives in `--desc`.

## Task standard

Task titles start with a verb and name the target. `--desc` carries the
technical how: approach, code references, inputs and prerequisites. Task-level
checklists are the definition of done:

```bash
lpui --actor NAME add-task --story S --title "Implement token rotation" --desc "Approach and file refs" --priority p0
lpui --actor NAME add-task --story S --title "Run the relevant test suites" --desc "Suites named in the interview" --priority p1
lpui --actor NAME add-task --story S --title "Refactor what the change touched" --desc "Leave the area cleaner" --priority p2
lpui --actor NAME add-task --story S --title "Clean up touched documentation" --desc "Docs matching the final code" --priority p2
lpui --actor NAME add-criteria --kind task --id T --text "Unit tests pass"
```

No assignee or effort fields — ownership is the `--actor` on each write, size
is the priority. Every task `--desc` names the technical approach and the inputs/prerequisites — a task missing either is not ready to cut. Cut tasks only from scouted ground: each one must name real files, real constraints, real prerequisites.

## Human-in-the-loop (preferred for judgment calls)

Scope, taste, and repo-wide impact belong to the human: ask in conversation
and wait for an answer before writing. Never decide a project's why/what or its acceptance criteria on your own — interview, record, confirm. Scout the codebase during the interview to target real files and constraints. Status moves and task execution are yours once the definition is agreed.

## Rules

- One DB write = one feed event; keep titles imperative and scoped.
- Prefer update/status over delete + recreate (ids and history survive).
- Never invent project/story ids: `lpui list` to discover them.
- Never `lpui seed` a real repo plan — it inserts demo data.
- The plan is the truth for the desired implementation: change it before changing course.
- Format for scanability: short headers, fenced code blocks, one concern per block, verdict first.
- Full verb reference: `lpui --help` (agents use the CLI; the TUI is keyboard-only).
"""

AGENTS_SNIPPET = """## lazyplan (`lpui`)

Repo plan of record: projects > stories > tasks in `.plan/lazyplan.db`.
Human watches `lpui ui`; agents work via the CLI with `--actor <name>`.

- New project? Interview the human first: vision, scope in and out, deliverables, constraints, metrics, acceptance criteria (priority only if volunteered; new tasks default p1). Scout the codebase during the interview.
- Read: `lpui list`, `lpui show --kind project --id N`, `lpui feed --limit 20` (`--json` for parsing)
- Write (full CRUD): `lpui add-project`, `lpui add-story`, `lpui add-task`, `lpui update`, `lpui status`, `lpui delete` (all with `--actor <name>`)
- Stories read As a/I want/so that with Given-When-Then criteria; tasks start with a verb and carry a DoD checklist; cut both from scouted ground only
- Scout before creating anything — no row from unscouted ground; scope lists what is in and out explicitly
- Plans include QA, refactoring, and documentation cleanup by default; ask about relevant testing in the interview, drop them only on explicit opt-out
- Done means: `lpui add-criteria --kind project`, cut stories, cut prioritized tasks, work p0 first
- Unsure on scope or taste? Ask the human in conversation — never guess the definition
- Review gate: present the plan, edit on the spot, execute only on check-off; the plan is the truth
- Full skill: `.agents/skills/lazyplan/SKILL.md` · verbs: `lpui --help`
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
    """Outcome of a skill install, serialized into `lpui init` JSON."""

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
    """Interactive `lpui init` wizard. All I/O on stderr/stdin; stdout stays JSON."""
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
    """True only for an interactive human `lpui init` with no scope overrides."""
    no_skills = bool(getattr(args, "no_skills", False))
    scope_arg = str(getattr(args, "skills_scope", "") or "").strip()
    yes = bool(getattr(args, "yes", False))
    as_json = bool(getattr(args, "json", False))
    if no_skills or scope_arg or yes or as_json or not is_tty:
        return False
    return True


def handle_init(args: Namespace, repo_root: Path | None, home: Path | None = None) -> dict:
    """Decide interactive vs non-interactive skill setup for `lpui init`."""
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
