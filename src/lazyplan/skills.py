"""Agent-skill installer for `lpui init`.

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
from argparse import Namespace
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from .repo import PLAN_DIR
from .templates import (
    TEMPLATE_FILES,
    TemplateChoices,
    run_template_setup,
)

SKILL_NAME = "lazyplan"

AGENTS_DIR = ".agents"
SKILLS_DIR = "skills"

AGENTS_MARK_BEGIN = "<!-- lazyplan:start -->"
AGENTS_MARK_END = "<!-- lazyplan:end -->"

# -- `lpui init` skill-wizard text (wizard prints these; keep wording stable) --
INIT_SKILLS_TITLE = "== lpui init: agent skills =="
INIT_SKILLS_EXPLAIN = "One universal skill teaches your agents to use `lpui` for planning."
INIT_SKILLS_COVERAGE = (
    "Writes one copy per selected agent into that agent's own skills folder "
    "(e.g. `~/.config/opencode/skills/lazyplan/`). Tools without a known "
    "folder share `~/.agents/skills/lazyplan/`."
)
INIT_SKILLS_DONE = "Done. Restart your agent session, then try `lpui list`."
INIT_SKILLS_COMMIT_TIP = (
    "Tip: commit `.agents/skills/lazyplan/`, `.claude/skills/` (if any), and AGENTS.md."
)


# -- `lpui init` template-setup text (wizard prints these; keep wording stable) --
TEMPLATE_SETUP_TITLE = "== lpui init: creation templates =="
TEMPLATE_SETUP_EXPLAIN = (
    "`.agents/lazyplan/templates/` defines what new plans, milestones, and tasks look "
    "like: defaults fill empty flags, required fields fail creation naming the "
    "field, long single-blob text fails creation until it uses paragraphs and "
    "sections. Answer three questions to tailor the "
    "starters (silent runs use the opinionated defaults)."
)
TEMPLATE_REVIEW = "Review existing templates in .agents/lazyplan/templates/?"
TEMPLATE_Q_WHYWHAT = "Require plan why and what on creation?"
TEMPLATE_Q_DESC = "Require milestone/task details (desc)?"
TEMPLATE_Q_PRIORITY = "Default task priority? [p0/p1/p2/p3] (default p1): "
TEMPLATE_DONE = "Templates settled — edit `.agents/lazyplan/templates/*.md` any time."

SKILL_FRONTMATTER = """---
name: lazyplan
description: Plan and track work with lazyplan (lpui) — interview for a plan's why/what/acceptance criteria, then cut prioritized milestones and tasks. Use when the user asks to plan work, track progress, break down a feature, check status, or when repo instructions mention `lpui`.
license: MIT
compatibility: opencode, claude-code, codex, gemini-cli, cursor
---
"""

SKILL_BODY = """# lazyplan (`lpui`) — local plan journal

`lpui` is the repo's plan of record: plans > milestones > tasks, stored in
`.agents/lazyplan/lazyplan.db` (SQLite, committed with the repo or local — check
`.agents/lazyplan/config.json`). The human watches `lpui ui`; agents inject work through
the CLI. Never touch the TUI process — only call `lpui`.

A plan is: title + priority + why + what + acceptance criteria. Milestones cut
a plan into slices; tasks cut a milestone into prioritized units of work. That
is the whole model — no dates, owners, labels, or estimates.

## Identity

Pass `--actor <name>` on every write so the human sees who did what in
`lpui feed` (e.g. `lpui --actor opencode add-task ...`). Reads don't need it.
`--actor` and `--json` work before or after the verb
(`lpui list --json` == `lpui --json list`).

## DB scoping (first match wins)

`--db PATH` → `$LAZYPLAN_DB` → nearest team-initialized
`.agents/lazyplan/lazyplan.db` walking up (only when `lpui init --team`
created it) → shared `~/.lazyplan/lazyplan.db`
(`%LOCALAPPDATA%/lazyplan/lazyplan.db` on Windows).
`lpui init` defaults to the shared home: no repo writes, skills installed
per agent, one database everybody shares. Pass `--team` (or
`--skills-scope project|both`) to opt a repo into shared storage
(`.agents/lazyplan/`, repo skills, `AGENTS.md` pointer, templates).
Don't override `--db` unless asked.

## Linked repos (central plan, many checkouts)

Plans, milestones, and tasks each link 0..n repo checkouts so one central
DB can plan work across repos. A row with no explicit links inherits:
a task inherits its milestone's effective repos, a milestone inherits its
plan's. Link by absolute checkout path plus remote URL (auto-detected
from `git remote get-url origin` when omitted):

```bash
lpui --actor NAME link-repo --kind plan --id P --repo /path/to/checkout [--remote URL]
lpui --actor NAME unlink-repo --kind plan --id P --repo /path/to/checkout
lpui repos --kind task --id T [--effective]    # explicit vs inherited
lpui list --repo /path/to/checkout             # only matching rows
```

`show`, `list --json`, and `export` include `repos` plus `effective_repos`.

## Starting a plan: interview first

Never invent a plan's definition. When the user asks to plan something,
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
`--what`; acceptance criteria become plan-level checklist items. There are
no stakeholder, owner, or estimate fields — if it does not fit why, what, or
criteria, it does not belong in the definition.

## Implementation requests: close the ambiguity gap

When the user asks to build, implement, or change something, run the
interview above as an ambiguity hunt before writing any row. Do not accept
"implement X" at face value — pin down all of these in conversation:

- Scope: explicit in-scope and out-of-scope lists, in plain language.
- Touch-points: the files, commands, and surfaces involved (scouted, real paths).
- Edge cases and non-goals: what must keep working, what is explicitly excluded.
- Assumptions: what you take for granted, stated so the human can correct it.

Vague scope is rejected, not recorded. No row is written from unscouted
ground, in any case, no exceptions.

## Readability: structure every row

Write every plan why/what, milestone desc, and task desc for scanning:
short paragraphs separated by blank lines, sections with headers or lists
where needed. Creation rejects long single-blob text (over 300 chars with
no paragraph breaks or section markers) — split it into paragraphs and
sections. Short one-liners stay legal. Never ship bracket, example, or
placeholder text as content or criteria — starters ship empty on purpose,
and the interview must fill them with real words.

While interviewing, scout the codebase (explore agents, grep, file reads) so
each question clears up real ambiguity: what exists, what constrains the
approach, what the deliverables touch. Never cut work from an unscouted
definition. Scouting is mandatory before creating anything — plan, milestone,
or task. No row is written from unscouted ground, in any case, no exceptions.
Then record it:

```bash
lpui --actor NAME add-plan --title "API v2" --why ".." --what ".." --priority p1
lpui --actor NAME add-criteria --kind plan --id P --text "Works offline"
lpui criteria --kind plan --id P                                     # list items
lpui check --id C / lpui uncheck --id C                                 # tick/untick (advisory)
```

Only once the definition is agreed, cut the work — milestones from the plan,
then prioritized tasks from each milestone, shaped as below plus the default QA,
refactor, and documentation tasks.

Every plan carries QA testing tasks, a refactoring task, and documentation
cleanup by default, shaped by the interview's testing answer. Ground every QA task in the acceptance criteria: each criterion is exercised by a named test task, and DoD checklists reference the criteria they satisfy. Only an explicit user opt-out ("skip QA", "no refactoring") excludes them — silence means include.

Work top priority first. Move rows through todo → doing → done as you go.

## Review gate: plan is truth

Once the definition is recorded and the work is cut, present the plan for check-off before implementing anything:

```bash
lpui list --status all                 # the whole tree
lpui show --kind plan --id P        # why/what + criteria + children
```

Walk the human through every milestone and task, make last edits on the spot, and start executing only on explicit check-off. During execution the plan stays the truth: fold new findings into the plan before changing code, never around it.

## Read first

```bash
lpui list [--status todo|doing|done|all] [--archived] [--plan ID] [--priority p0]  # tree (default: all)
lpui show --kind plan|milestone|task --id N                           # full context
lpui feed --limit 20                                                 # recent activity
lpui export --format json                                            # full dump when you need everything
lpui info                                                            # resolved db path + counts (scope debugging)
lpui reconcile                                                       # recompute parent statuses from children
```

Add `--json` for machine-parseable output (`lpui list --json`).

## Templates (per-repo creation defaults)

`.agents/lazyplan/templates/{plan,milestone,task}.md` (scaffolded by `lpui init --team`,
commit them to share) define what new rows look like. Team repos share them;
otherwise templates live beside the shared home DB at `~/.lazyplan/templates/`.
Each file is Markdown
with YAML frontmatter; the body is guidance and ignored:

```yaml
defaults: {why: "", what: "", priority: ""}   # filled when a flag is empty
required: [title]                             # must be non-empty after fill
criteria: []                                  # starters ship empty: add real criteria per row
```

Long single-blob `why`/`what`/`desc` (over 300 chars with no paragraph
breaks or section markers) fails creation — use paragraphs and sections.
Field names are per kind: plan `title/why/what/priority`, milestone and task
`title/desc/priority`. Missing `required` entries fail with exit 2 naming the
field; missing template files mean legacy behavior (tasks default `p1`).

`lpui init` walks the user through template setup: on a TTY it asks three
convention questions (require plan why/what, require milestone/task desc,
default task priority) and writes tailored
starters; `--yes`/`--json`/non-TTY writes the opinionated defaults silently.
Rerunning `init` on a TTY offers per-file keep/edit/reset (default keep) —
edits are never overwritten without an explicit reset.

## Write: full CRUD

Every entity supports create → read (`show`) → update/status → delete.
`--kind` is plan|milestone|task everywhere it appears.

```bash
lpui --actor NAME add-plan --title "API v2" --why ".." --what ".." --priority p1
lpui --actor NAME add-milestone --plan P --title "Feature Y" [--desc .. --priority p0]
lpui --actor NAME add-task --milestone S --title "Do X" [--desc ctx --priority p1]
lpui --actor NAME update --kind task --id T [--title .. --desc .. --priority p0|none]
lpui --actor NAME update --kind plan --id P [--title .. --what .. --why .. --priority p0|none]
lpui --actor NAME status --kind task --id T --to doing|done
lpui --actor NAME delete --kind task --id T                          # immediate, no confirm
```

Deleting a plan removes its milestones and tasks — double-check ids first.
Status moves roll parents up automatically: closing the last open task
completes its milestone and plan. Closing with open acceptance criteria warns
but never blocks.

## Acceptance criteria

```bash
lpui --actor NAME add-criteria --kind plan --id P --text "Works offline"  # acceptance item
lpui criteria --kind plan --id P                                          # list items
lpui check --id C / lpui uncheck --id C                                      # tick/untick (advisory)
lpui --actor NAME delete-criteria --id C
lpui --actor NAME import --file dump.json                                    # load an export dump (remaps ids)
```

Criteria live on plans, milestones, and tasks. Plan-level criteria are the
definition of done — tick them as the work lands.

## Milestone standard

Each milestone states user value in narrative form, with testable criteria:

```bash
lpui --actor NAME add-milestone --plan P --title "Feature Y" --desc "As a [persona], I want [action] so that [benefit]" --priority p1
lpui --actor NAME add-criteria --kind milestone --id S --text "Given [context], when [action], then [outcome]"
```

Keep milestones INVEST: independent, negotiable, valuable, estimable, small,
testable. At creation, `--desc` carries the narrative plus the INVEST check
and the inputs/prerequisites — a milestone without them is not ready to cut. No
dependency, estimate, or owner fields — sequencing lives in priority order
(work p0 first), context lives in `--desc`.

## Task standard

Task titles start with a verb and name the target. `--desc` carries the
technical how: approach, code references, inputs and prerequisites. Task-level
checklists are the definition of done:

```bash
lpui --actor NAME add-task --milestone S --title "Implement token rotation" --desc "Approach and file refs" --priority p0
lpui --actor NAME add-task --milestone S --title "Run the relevant test suites" --desc "Suites named in the interview" --priority p1
lpui --actor NAME add-task --milestone S --title "Refactor what the change touched" --desc "Leave the area cleaner" --priority p2
lpui --actor NAME add-task --milestone S --title "Clean up touched documentation" --desc "Docs matching the final code" --priority p2
lpui --actor NAME add-criteria --kind task --id T --text "Unit tests pass"
```

No assignee or effort fields — ownership is the `--actor` on each write, size
is the priority. Every task `--desc` names the technical approach and the inputs/prerequisites — a task missing either is not ready to cut. Cut tasks only from scouted ground: each one must name real files, real constraints, real prerequisites.

## Human-in-the-loop (preferred for judgment calls)

Scope, taste, and repo-wide impact belong to the human: ask in conversation
and wait for an answer before writing. Never decide a plan's why/what or its acceptance criteria on your own — interview, record, confirm. Scout the codebase during the interview to target real files and constraints. Status moves and task execution are yours once the definition is agreed.

## Rules

- One DB write = one feed event; keep titles imperative and scoped.
- Prefer update/status over delete + recreate (ids and history survive).
- Never invent plan/milestone ids: `lpui list` to discover them.
- Never `lpui seed` a real repo plan — it inserts demo data.
- The plan is the truth for the desired implementation: change it before changing course.
- Format for scanability: short headers, fenced code blocks, one concern per block, verdict first.
- Full verb reference: `lpui --help` (agents use the CLI; the TUI is keyboard-only).
"""

AGENTS_SNIPPET = """## lazyplan (`lpui`)

Repo plan of record: plans > milestones > tasks in `.agents/lazyplan/lazyplan.db`.
Human watches `lpui ui`; agents work via the CLI with `--actor <name>`.

- New plan? Interview the human first: vision, scope in and out, deliverables, constraints, metrics, acceptance criteria (priority only if volunteered; new tasks default p1). Scout the codebase during the interview.
- Read: `lpui list`, `lpui show --kind plan --id N`, `lpui feed --limit 20` (`--json` for parsing)
- Write (full CRUD): `lpui add-plan`, `lpui add-milestone`, `lpui add-task`, `lpui update`, `lpui status`, `lpui delete` (all with `--actor <name>`)
- Milestones read As a/I want/so that with Given-When-Then criteria; tasks start with a verb and carry a DoD checklist; cut both from scouted ground only
- Scout before creating anything — no row from unscouted ground; scope lists what is in and out explicitly
- Implementation requests get an ambiguity hunt first: touch-points, edge cases, non-goals, assumptions — never accept "implement X" at face value
- Write every row for scanning: paragraphs and sections, no single-blob text, no placeholder content; starters ship empty, fill them with real words
- Templates in `.agents/lazyplan/templates/` fill/enforce/auto-add criteria at creation; missing templates mean legacy defaults; `lpui init` walks through setup, reruns offer keep/edit/reset
- Plans include QA, refactoring, and documentation cleanup by default; ask about relevant testing in the interview, drop them only on explicit opt-out
- Done means: `lpui add-criteria --kind plan`, cut milestones, cut prioritized tasks, work p0 first
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
        raw = gi.read_text() if gi.is_file() else ""
    except OSError:
        return False
    lines = [ln.strip().rstrip("/") for ln in raw.splitlines()]
    if entry.rstrip("/") in lines:
        return False
    try:
        with open(gi, "a") as fh:
            if raw and not raw.endswith("\n"):
                fh.write("\n")
            fh.write(entry + "\n")
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


def _ask_template_choices(read: Callable[[], str] | None, out: TextIO) -> TemplateChoices:
    """Three convention questions (EOF/empty means the opinionated default)."""
    require_why_what = prompt_confirm(TEMPLATE_Q_WHYWHAT, read=read, write=out)
    require_desc = prompt_confirm(TEMPLATE_Q_DESC, read=read, write=out)
    pri = _prompt(
        TEMPLATE_Q_PRIORITY,
        valid={"p0", "p1", "p2", "p3", ""},
        default="p1",
        read=read,
        write=out,
    )
    return TemplateChoices(
        require_why_what=require_why_what,
        require_desc=require_desc,
        task_priority=pri or "p1",
    )


def run_template_phase(
    plan_dir: Path | None,
    read: Callable[[], str] | None = None,
    write: TextIO | None = None,
) -> dict[str, list[str]] | None:
    """Interactive template setup for the wizard; None when not repo-scoped."""
    import sys

    if plan_dir is None:
        return None
    out: TextIO = write if write is not None else sys.stderr
    tdir = plan_dir / "templates"
    existing = [k for k, f in TEMPLATE_FILES.items() if (tdir / f).is_file()]
    print(f"\n{TEMPLATE_SETUP_TITLE}", file=out)
    print(TEMPLATE_SETUP_EXPLAIN, file=out)
    if existing:
        if not prompt_confirm(TEMPLATE_REVIEW, default_yes=False, read=read, write=out):
            return run_template_setup(plan_dir, interactive=False)
    choices = _ask_template_choices(read, out)
    summary = run_template_setup(plan_dir, interactive=True, choices=choices, read=read, write=out)
    for key in ("added", "reset"):
        for line in summary[key]:
            print(f"  template: {line} ({key})", file=out)
    print(TEMPLATE_DONE, file=out)
    return summary


def _report_detected(hosts: list[AgentHost], out: TextIO) -> None:
    """Print which agent hosts were found on this machine (names only)."""
    found = [h for h in hosts if h.detected]
    if found:
        print("Detected on this machine:", file=out)
        for h in found:
            print(f"  [x] {h.label}", file=out)
        missing = [h.label for h in hosts if not h.detected]
        if missing:
            print(f"Not found (still covered): {', '.join(missing)}", file=out)
    else:
        print(
            "No agent CLIs detected — the universal skill still works when you install one.",
            file=out,
        )


def _ask_tools(
    hosts: list[AgentHost],
    read: Callable[[], str] | None,
    out: TextIO,
) -> list[str]:
    """Ask which agents to install for; returns tool keys (names only, no paths)."""
    valid = [h.key for h in hosts if h.key in KNOWN_TOOLS]
    print("", file=out)
    print("Which agents should get the skill?", file=out)
    for i, key in enumerate(valid, start=1):
        host = next(h for h in hosts if h.key == key)
        mark = "x" if host.detected else " "
        print(f"  {i}) [{mark}] {host.label}", file=out)
    print("Pick numbers/keys separated by space, 'all', or Enter for detected.", file=out)
    raw = _prompt(
        "Agents [detected]: ",
        valid=None,
        default="",
        read=read,
        write=out,
    )
    return parse_tool_selection(raw, hosts)


def _local_skill_dirs(picked: list[str], home: Path) -> list[Path]:
    """Resolved local install dirs for picked tools (one per tool)."""
    return [d.parent for d in global_skill_targets(picked, home)]


def _ask_install_paths(
    picked: list[str],
    repo_root: Path | None,
    home: Path,
    read: Callable[[], str] | None,
    out: TextIO,
) -> tuple[str, str | None]:
    """Dictate where skills land; returns (scope, custom skills-dir override)."""
    print("", file=out)
    print("Where should the skills be installed?", file=out)
    print("  Local default (no repo writes):", file=out)
    for d in _local_skill_dirs(picked, home):
        print(f"    - {d}/", file=out)
    print("  1) Local    (use these paths)", file=out)
    if repo_root is not None:
        print("  2) Team     (repo-shared dirs — commit them)", file=out)
    else:
        print("  2) Team     (unavailable — not inside a git repo)", file=out)
    print("  3) Both     (local + team)", file=out)
    print("  4) Custom   (type a folder below)", file=out)
    print("  5) Skip     (DB only, no skill files)", file=out)
    choice = _prompt(
        "Pick [1/2/3/4/5] (default 1): ",
        valid={"1", "2", "3", "4", "5"},
        default="1",
        read=read,
        write=out,
    )
    if choice == "4":
        custom = _prompt(
            "Custom skills folder: ",
            valid=None,
            default="",
            read=read,
            write=out,
        ).strip()
        if not custom:
            print("Empty — using local defaults.", file=out)
            return "global", None
        return "global", str(Path(custom).expanduser())
    scope = {"1": "global", "2": "project", "3": "both", "5": "none"}[choice]
    if scope == "project" and repo_root is None:
        print("Not in a repo — installing locally instead.", file=out)
        scope = "global"
    return scope, None


def _ask_agents_md(
    scope: str,
    repo_root: Path | None,
    read: Callable[[], str] | None,
    out: TextIO,
) -> bool:
    """Ask whether to patch repo AGENTS.md (project scopes only)."""
    if scope in ("project", "both") and repo_root is not None:
        ans = _prompt(
            "Add the `## lazyplan` pointer to repo AGENTS.md? [Y/n]: ",
            valid={"y", "n", "Y", "N", ""},
            default="Y",
            read=read,
            write=out,
        )
        return ans.lower() != "n"
    return False


def _report_install(result: InstallResult, out: TextIO) -> None:
    """Print what the install wrote."""
    for line in result.installed:
        print(f"  skill: {line}", file=out)
    if result.updated_agents_md:
        print(f"  agents-md: {result.updated_agents_md}", file=out)


def run_wizard(
    repo_root: Path | None,
    home: Path | None = None,
    read: Callable[[], str] | None = None,
    write: TextIO | None = None,
    plan_dir: Path | None = None,
) -> InstallResult:
    """Interactive `lpui init` wizard. All I/O on stderr/stdin; stdout stays JSON."""
    import sys

    home = home or Path.home()
    out: TextIO = write if write is not None else sys.stderr
    hosts = detect_agents(home)

    print(f"\n{INIT_SKILLS_TITLE}", file=out)
    print(INIT_SKILLS_EXPLAIN, file=out)
    _report_detected(hosts, out)
    print(INIT_SKILLS_COVERAGE, file=out)

    picked = _ask_tools(hosts, read, out)
    scope, skills_override = _ask_install_paths(picked, repo_root, home, read, out)
    if scope == "none":
        print("Skipped skill setup — DB is ready.", file=out)
        return InstallResult(scope=scope, skipped="user skipped skill setup")

    with_claude = "claude" in picked
    if with_claude and skills_override is None:
        print("Also writing the `.claude/skills/` copy.", file=out)

    with_md = _ask_agents_md(scope, repo_root, read, out)

    result = install(
        scope,
        repo_root,
        home,
        with_claude_copy=False,
        tools=picked,
        with_agents_md=with_md,
        skills_dir=skills_override,
    )
    for dest_line in list(result.installed):
        dest = dest_line.rsplit(" (", 1)[0]
        try:
            ensure_skill_db(dest)
        except OSError:
            pass
    _report_install(result, out)
    if scope in ("project", "both") and repo_root is not None:
        resolved = plan_dir or (repo_root / PLAN_DIR)
        result.templates = run_template_phase(resolved, read, out)
    print(INIT_SKILLS_DONE, file=out)
    if scope in ("project", "both"):
        print(INIT_SKILLS_COMMIT_TIP, file=out)
    _ = sys  # keep import local to this function
    return result


def should_prompt(args: Namespace, is_tty: bool) -> bool:
    """True only for an interactive human `lpui init` with no scope overrides."""
    no_skills = bool(getattr(args, "no_skills", False))
    scope_arg = str(getattr(args, "skills_scope", "") or "").strip()
    team = bool(getattr(args, "team", False))
    agents = str(getattr(args, "agents", "") or "").strip()
    yes = bool(getattr(args, "yes", False))
    as_json = bool(getattr(args, "json", False))
    if no_skills or scope_arg or team or agents or yes or as_json or not is_tty:
        return False
    return True


def _skills_dir_override(args: Namespace) -> str | None:
    """Explicit skill dir: --skills-dir wins, then $LAZYPLAN_SKILLS_DIR."""
    flag = str(getattr(args, "skills_dir", "") or "").strip()
    if flag:
        return flag
    env = os.environ.get("LAZYPLAN_SKILLS_DIR", "").strip()
    return env or None


def _install_for_scope(
    scope: str,
    repo_root: Path | None,
    home: Path,
    override: str | None,
    tools: list[str] | None = None,
) -> InstallResult:
    """Detect hosts and install to scope (shared by flag and --yes paths)."""
    hosts = detect_agents(home)
    if tools is None:
        with_claude = any(h.key == "claude" and h.detected for h in hosts)
        native = [h.key for h in hosts if h.detected and h.key in KNOWN_TOOLS]
        if not native:
            # Bare machine: --yes means the opinionated defaults, not nothing.
            native = ["opencode"]
    else:
        with_claude = False
        # Keep every known tool: tools without a native folder (copilot)
        # fall back to the shared ~/.agents/skills dir in global_skill_targets.
        native = [t for t in tools if t in KNOWN_TOOLS]
    res = install(
        scope,
        repo_root,
        home,
        with_claude_copy=with_claude,
        tools=native,
        skills_dir=override,
    )
    for dest_line in list(res.installed):
        dest = dest_line.rsplit(" (", 1)[0]
        try:
            ensure_skill_db(dest)
        except OSError:
            pass
    return res


def _agents_override(args: Namespace) -> list[str] | None:
    """Explicit agent list: --agents wins, then $LAZYPLAN_AGENTS."""
    flag = str(getattr(args, "agents", "") or "").strip()
    if not flag:
        flag = os.environ.get("LAZYPLAN_AGENTS", "").strip()
    if not flag:
        return None
    if flag.lower() in ("all", "*"):
        return list(KNOWN_TOOLS)
    return [p.strip().lower() for p in flag.replace(",", " ").split() if p.strip()]


def handle_init(
    args: Namespace,
    repo_root: Path | None,
    home: Path | None = None,
    plan_dir: Path | None = None,
) -> dict:
    """Decide interactive vs non-interactive skill setup for `lpui init`."""
    import sys

    home = home or Path.home()
    no_skills = bool(getattr(args, "no_skills", False))
    scope_arg = str(getattr(args, "skills_scope", "") or "").strip()
    team = bool(getattr(args, "team", False))
    # Zero-touch default: local-only unless team opt-in.
    # Legacy --skills-scope project/both still means team repo writes.
    if team and not scope_arg:
        scope_arg = "project"
    tools = _agents_override(args)
    yes = bool(getattr(args, "yes", False))
    if no_skills or scope_arg == "none":
        return InstallResult(scope="none", skipped="--no-skills").to_dict()
    if scope_arg in ("project", "global", "both"):
        res = _install_for_scope(scope_arg, repo_root, home, _skills_dir_override(args), tools)
        return res.to_dict()
    if yes:
        res = _install_for_scope("global", repo_root, home, _skills_dir_override(args), tools)
        return res.to_dict()
    is_tty = bool(sys.stdin.isatty() and sys.stdout.isatty())
    if should_prompt(args, is_tty):
        try:
            return run_wizard(repo_root, home, plan_dir=plan_dir).to_dict()
        except (EOFError, KeyboardInterrupt, OSError):
            return InstallResult(scope="none", skipped="non-interactive").to_dict()
    # Non-interactive default: shared-home install (never repo writes).
    if _skills_dir_override(args) is not None or tools is not None or team:
        scope = scope_arg if scope_arg in ("project", "global", "both") else "global"
        if team and scope == "global":
            scope = "project"
        res = _install_for_scope(scope, repo_root, home, _skills_dir_override(args), tools)
        return res.to_dict()
    reason = "--json (machine output)" if bool(getattr(args, "json", False)) else "non-interactive"
    if os.environ.get("LAZYPLAN_NO_SKILLS", "").strip():
        reason = "$LAZYPLAN_NO_SKILLS"
    return InstallResult(scope="none", skipped=reason).to_dict()
