"""Per-repo creation templates: `.agents/lazyplan/templates/{plan,milestone,task}.md`.

Users edit these files (scaffolded by `lpui init`) to define what new
plans, milestones, and tasks look like: default field values, required
fields, and criteria auto-added at creation. Stdlib only.

File shape (Markdown + YAML frontmatter; body is guidance, ignored):

    ---
    defaults:
      why: ""
      what: ""
    required: [title]
    criteria:
      - "Works offline"
    ---
    # guidance for editors (ignored by the loader)

Canonical field names per kind:
  plan:      title, why, what
  milestone: title, desc
  task:      title, desc

Behavior:
  fill     — empty creation flags fall back to template defaults.
  enforce  — required fields still empty after fill raise ValueError naming
             the field (CLI surfaces exit 2).
  criteria — template criteria rows are added after a successful create.
Missing files mean legacy behavior (no defaults, no enforcement, no
auto-criteria). Only repo-scoped DBs (`.agents/lazyplan/` or legacy `.plan/`)
read templates; global/explicit DBs elsewhere never do.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO

from .kinds import KIND_ERROR
from .repo import LEGACY_PLAN_DIR, is_repo_plan_dir

TEMPLATE_DIRNAME = "templates"

TEMPLATE_FILES: dict[str, str] = {
    "plan": "plan.md",
    "milestone": "milestone.md",
    "task": "task.md",
}

FIELDS_BY_KIND: dict[str, tuple[str, ...]] = {
    "plan": ("title", "why", "what"),
    "milestone": ("title", "desc"),
    "task": ("title", "desc"),
}

FLAG_BY_FIELD: dict[str, str] = {
    "title": "--title",
    "why": "--why",
    "what": "--what",
    "desc": "--desc",
}


@dataclass
class TemplateChoices:
    """Answers shaping freshly written starters (silent runs use the defaults)."""

    require_why_what: bool = True
    require_desc: bool = True
    # Legacy switch: starter criteria lists are empty, so fresh rows ship
    # with zero auto-added criteria and the interview must add real ones.
    # Kept so old callers constructing TemplateChoices keep working.
    with_examples: bool = False


# Readability gate: long free text must be structured (paragraphs/sections),
# never a single blob. Short one-liners stay legal.
READABILITY_THRESHOLD = 300

SECTION_MARKERS = ("#", "- ", "* ", "> ", "1.", "2.", "3.", "4.", "5.")


def _is_sectioned(value: str) -> bool:
    """True when text has paragraph breaks or section/list markers."""
    if "\n\n" in value:
        return True
    return any(line.lstrip().startswith(SECTION_MARKERS) for line in value.splitlines())


def check_readable(kind: str, field: str, value: str) -> None:
    """Reject long single-blob text; raises naming the field. Short text passes."""
    if field not in ("why", "what", "desc"):
        return
    if value and len(value) > READABILITY_THRESHOLD and not _is_sectioned(value):
        flag = FLAG_BY_FIELD.get(field, field)
        raise ValueError(
            f"template {kind}.md requires readable '{field}' "
            f"(over {READABILITY_THRESHOLD} chars with no paragraphs or sections) "
            f"— split into paragraphs and sections, then pass {flag} again"
        )


def _frontmatter(defaults: dict[str, str], required: list[str], criteria: list[str]) -> str:
    """Render a frontmatter block (keys quoted only when needed)."""

    lines = ["---", "defaults:"]
    for key, value in defaults.items():
        lines.append(f'  {key}: "{value}"')
    lines.append(f"required: [{', '.join(required)}]")
    if criteria:
        lines.append("criteria:")
        for item in criteria:
            lines.append(f'  - "{item}"')
    else:
        lines.append("criteria: []")
    lines.append("---")
    return "\n".join(lines) + "\n"


PLAN_BODY = """
# plan template — edit the frontmatter above; everything below is guidance.

How `add-plan` (and the TUI create command) uses this file:
- `defaults`: fills any flag you leave empty (`--why`, `--what`).
- `required`: must be non-empty after fill, or creation fails naming the
  field. Keep `why`/`what` here so every plan records its purpose; drop
  them to allow one-liner plans.
- `criteria`: acceptance rows auto-added to every new plan. Fresh starters
  ship EMPTY on purpose: the interview must add real, measurable criteria
  per plan (never ship bracket or example text as acceptance).

Implementation interrogation (run before any row is written): pin down
explicit in-scope and out-of-scope lists, the files/touch-points involved,
edge cases, non-goals, and assumptions. Vague scope is rejected, not recorded.

Commit strategy: state the ordered slices of small commits in `what`, and the
check that keeps each commit green. Do not plan one batch commit for the whole
plan.

Readability (enforced): write `why`/`what` for scanning — short paragraphs
separated by blank lines, sections with headers or lists where needed
(e.g. Scope in/out, Deliverables in order, Constraints/assumptions,
Metrics). Long single-blob text is rejected at creation; short one-liners
stay legal.

Example: to require only a title, set `required: [title]`.
"""

MILESTONE_BODY = """
# milestone template — edit the frontmatter above; everything below is guidance.

How `add-milestone` (and the TUI create command) uses this file:
- `defaults`: `desc` should carry the narrative plus the INVEST check, the
  inputs/prerequisites, and the ordered commit slices, e.g. `As a [persona],
  I want [action] so that [benefit]`. A milestone without them is not ready
  to cut.
- `required`: keep `desc` here so slices always carry user value; drop it to
  allow title-only milestones.
- `criteria`: Given/When/Then rows auto-added to every new milestone.
  Fresh starters ship EMPTY on purpose: add real, measurable criteria per
  milestone (e.g. `Given [context], when [action], then [outcome]` with
  concrete values, never brackets). Each criterion must be exercisable by a
  named task.

Commit order: map each task to the slice it advances.

Readability (enforced): structure `desc` in paragraphs and sections —
narrative first, then inputs/prerequisites. Long single-blob text is
rejected at creation; short descs stay legal.

Example: to require only a title, set `required: [title]`.
"""

TASK_BODY = """
# task template — edit the frontmatter above; everything below is guidance.

How `add-task` (and the TUI create command) uses this file:
- `defaults`: `desc` must carry the technical how in sections: Approach,
  code references, inputs/prerequisites, and the expected commit slice —
  a task missing them is not ready to cut. Name real files, real
  constraints, real prerequisites: cut tasks only from scouted ground.
- `required`: keep `desc` here so tasks always carry context; drop it to
  allow title-only tasks. Titles start with a verb naming the target.
- `criteria`: definition-of-done rows auto-added to every new task. Fresh
  starters ship EMPTY on purpose: add DoD checklists per task, each one
  referencing the plan criterion it satisfies (never ship example text).

Commit slice: one task lands as one or more small commits. Every commit is green — the relevant checks pass and the tree builds — and independently reviewable. Name what each commit proves and the verification that keeps it green.

Readability (enforced): structure `desc` in paragraphs and sections.
Long single-blob text is rejected at creation; short descs stay legal.

Example: to require only a title, set `required: [title]`.
"""

# Fresh starters ship with zero auto-added criteria: the planning interview
# must add real, measurable criteria per row. Never put placeholder or
# example text here — it would ship as fake acceptance.
PLAN_EXAMPLES: list[str] = []

MILESTONE_EXAMPLES: list[str] = []

TASK_EXAMPLES: list[str] = []


def render_starter(kind: str, choices: TemplateChoices) -> str:
    """Full starter file text for a kind, tailored by wizard choices."""
    if kind == "plan":
        required = ["title", "why", "what"] if choices.require_why_what else ["title"]
        fm = _frontmatter(
            {"why": "", "what": ""},
            required,
            list(PLAN_EXAMPLES) if choices.with_examples else [],
        )
        return fm + PLAN_BODY
    if kind == "milestone":
        required = ["title", "desc"] if choices.require_desc else ["title"]
        fm = _frontmatter(
            {"desc": ""},
            required,
            list(MILESTONE_EXAMPLES) if choices.with_examples else [],
        )
        return fm + MILESTONE_BODY
    if kind == "task":
        required = ["title", "desc"] if choices.require_desc else ["title"]
        fm = _frontmatter(
            {"desc": ""},
            required,
            list(TASK_EXAMPLES) if choices.with_examples else [],
        )
        return fm + TASK_BODY
    raise ValueError(KIND_ERROR)


OPINIONATED = TemplateChoices()

STARTERS: dict[str, str] = {
    kind: render_starter(kind, OPINIONATED) for kind in ("plan", "milestone", "task")
}


@dataclass
class Template:
    """Parsed template for one kind (empty = legacy behavior)."""

    kind: str
    defaults: dict[str, str] = field(default_factory=dict)
    required: list[str] = field(default_factory=list)
    criteria: list[str] = field(default_factory=list)


def templates_dir_for_db(db_path: str | Path) -> Path | None:
    """Templates dir for a DB path, or None (global/explicit DBs: no templates)."""
    parent = Path(db_path).expanduser().parent
    if is_repo_plan_dir(parent) or parent.name == LEGACY_PLAN_DIR:
        return parent / TEMPLATE_DIRNAME
    return None


def ensure_templates(plan_dir: str | Path, choices: TemplateChoices | None = None) -> list[str]:
    """Scaffold starter templates (idempotent: never overwrites edits)."""
    picks = choices or OPINIONATED
    d = Path(plan_dir).expanduser() / TEMPLATE_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for kind, filename in TEMPLATE_FILES.items():
        dest = d / filename
        if not dest.exists():
            dest.write_text(render_starter(kind, picks))
            written.append(str(dest))
    return written


def _split_body(text: str) -> tuple[str, str]:
    """Frontmatter and body of a template file (body may be empty)."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return "", text
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "".join(lines[: i + 1]), "".join(lines[i + 1 :])
    return "", text


def edit_template(path: str | Path, kind: str, choices: TemplateChoices) -> bool:
    """Rewrite one file's frontmatter from choices, preserving its criteria.

    Returns True when rewritten; False when the file is unparseable (kept).
    """
    dest = Path(path)
    try:
        current = parse_template(kind, dest.read_text())
    except (OSError, ValueError):
        return False
    _, body = _split_body(dest.read_text())
    if not body.strip():
        body = {"plan": PLAN_BODY, "milestone": MILESTONE_BODY, "task": TASK_BODY}[kind]
    if kind == "plan":
        required = ["title", "why", "what"] if choices.require_why_what else ["title"]
        defaults = {"why": "", "what": ""}
    elif kind == "milestone":
        required = ["title", "desc"] if choices.require_desc else ["title"]
        defaults = {"desc": ""}
    else:
        required = ["title", "desc"] if choices.require_desc else ["title"]
        defaults = {"desc": ""}
    dest.write_text(_frontmatter(defaults, required, current.criteria) + body)
    return True


def run_template_setup(
    plan_dir: str | Path,
    *,
    interactive: bool,
    choices: TemplateChoices | None = None,
    decisions: dict[str, str] | None = None,
    read: Callable[[], str] | None = None,
    write: TextIO | None = None,
) -> dict[str, list[str]]:
    """Settle template files; non-interactive is missing-only (never clobbers).

    Interactive mode re-offers per existing file (keep/edit/reset, default
    keep); only an explicit reset overwrites. `decisions` maps kind to
    keep|edit|reset for scripted runs (default keep). Returns
    {"added": [...], "kept": [...], "reset": [...]}.
    """
    picks = choices or OPINIONATED
    d = Path(plan_dir).expanduser() / TEMPLATE_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    summary: dict[str, list[str]] = {"added": [], "kept": [], "reset": []}
    for kind, filename in TEMPLATE_FILES.items():
        dest = d / filename
        if not dest.exists():
            dest.write_text(render_starter(kind, picks))
            summary["added"].append(str(dest))
            continue
        if not interactive:
            summary["kept"].append(str(dest))
            continue
        decision = (decisions or {}).get(kind, "").strip().lower()
        if not decision:
            decision = _ask_file(str(dest), read, write)
        if decision == "reset":
            dest.write_text(render_starter(kind, picks))
            summary["reset"].append(str(dest))
        elif decision == "edit":
            if edit_template(dest, kind, picks):
                summary["reset"].append(str(dest))
            else:
                summary["kept"].append(str(dest))
        else:
            summary["kept"].append(str(dest))
    return summary


def _ask_file(dest: str, read: Callable[[], str] | None, write: TextIO | None) -> str:
    """Keep/edit/reset choice for one existing file (default keep)."""
    ans = _prompt_file(
        f"{Path(dest).name} exists — keep, edit, or reset to fresh? [K/e/r]: ",
        read,
        write,
    )
    return {"e": "edit", "r": "reset"}.get(ans.lower(), "keep")


def _prompt_file(prompt: str, read: Callable[[], str] | None, write: TextIO | None) -> str:
    """Read one line (stderr/stdin); EOF means default/empty. Never raises."""
    import sys

    out: TextIO = write if write is not None else sys.stderr
    print(prompt, file=out, end="", flush=True)
    try:
        return (read() if read is not None else input()).strip()
    except (EOFError, KeyboardInterrupt, StopIteration):
        return ""


def _parse_list_inline(raw: str) -> list[str]:
    inner = raw.strip()[1:-1].strip()
    if not inner:
        return []
    return [p.strip().strip("'\"") for p in inner.split(",") if p.strip()]


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _frontmatter_lines(lines: list[str]) -> list[str]:
    """Frontmatter body lines; empty when the file has no frontmatter."""
    if not lines or lines[0].strip() != "---":
        # No frontmatter: legacy-empty template (body-only file).
        return []
    try:
        end = next(i for i, ln in enumerate(lines[1:], start=1) if ln.strip() == "---")
    except StopIteration as exc:
        raise ValueError("unclosed frontmatter (missing second ---)") from exc
    return lines[1:end]


def _section_header(raw: str, stripped: str) -> str | None:
    """Section name for a bare non-indented `key:` line, else None."""
    if raw.startswith((" ", "\t")):
        return None
    if stripped.endswith(":") and " " not in stripped:
        return stripped[:-1]
    return None


def _parse_inline_list(
    kind: str, field: str, lineno: int, rest: str
) -> tuple[list[str] | None, str | None]:
    """Parse `field: [...]` or `field:`; returns (items, new_section)."""
    if rest.startswith("["):
        return _parse_list_inline(rest), None
    if rest:
        raise ValueError(f"template {kind}.md line {lineno}: bad {field} list")
    return None, field


def _parse_section_entry(
    kind: str,
    section: str,
    stripped: str,
    lineno: int,
    allowed: set[str],
    defaults: dict[str, str],
    required: list[str],
    criteria: list[str],
) -> None:
    """Append one `- item` or `k: v` line to its section (mutates the lists)."""
    if section == "defaults":
        if ":" not in stripped:
            raise ValueError(f"template {kind}.md line {lineno}: bad default entry")
        k, _, v = stripped.partition(":")
        k, v = k.strip(), _strip_quotes(v)
        if k == "priority":
            return  # retired concept: old templates keep this key; ignore it
        if k not in allowed:
            raise ValueError(f"template {kind}.md line {lineno}: unknown field {k!r}")
        defaults[k] = v
        return
    if not stripped.startswith("- "):
        raise ValueError(f"template {kind}.md line {lineno}: bad {section} entry")
    if section == "required":
        name = _strip_quotes(stripped[2:])
        if name == "priority":
            return  # retired concept: ignore in old templates
        required.append(name)
        return
    item = _strip_quotes(stripped[2:]).strip()
    if item:
        criteria.append(item)


@dataclass
class _PartialTemplate:
    """Mutable parse state: one body line applies itself to these lists."""

    allowed: set[str]
    defaults: dict[str, str] = field(default_factory=dict)
    required: list[str] = field(default_factory=list)
    criteria: list[str] = field(default_factory=list)
    section: str | None = None

    def apply_header(self, kind: str, lineno: int, header: str) -> None:
        """Adopt a section header, rejecting unknown keys."""
        if header == "defaults":
            self.section = "defaults"
        elif header in ("required", "criteria"):
            self.section = header
        else:
            raise ValueError(f"template {kind}.md line {lineno}: unknown key {header!r}")

    def apply_inline_list(self, kind: str, field: str, lineno: int, rest: str) -> None:
        """Apply `field: [...]` (replaces, closes section) or bare `field:` (opens it)."""
        items, section = _parse_inline_list(kind, field, lineno, rest)
        if items is not None:
            if field == "required":
                self.required = items
            else:
                self.criteria = items
            self.section = None
        else:
            self.section = section

    def apply_line(self, kind: str, raw: str, stripped: str, lineno: int) -> None:
        """Process one frontmatter body line."""
        header = _section_header(raw, stripped)
        if header is not None:
            self.apply_header(kind, lineno, header)
            return
        if stripped.startswith("required:"):
            self.apply_inline_list(kind, "required", lineno, stripped[len("required:") :].strip())
            return
        if stripped.startswith("criteria:"):
            self.apply_inline_list(kind, "criteria", lineno, stripped[len("criteria:") :].strip())
            return
        if stripped.startswith("defaults:") and stripped != "defaults:":
            raise ValueError(f"template {kind}.md line {lineno}: bad defaults block")
        if self.section is None:
            raise ValueError(f"template {kind}.md line {lineno}: entry outside a section")
        _parse_section_entry(
            kind,
            self.section,
            stripped,
            lineno,
            self.allowed,
            self.defaults,
            self.required,
            self.criteria,
        )

    def validate(self, kind: str) -> None:
        """Cross-check required fields."""
        for name in self.required:
            if name not in self.allowed:
                raise ValueError(f"template {kind}.md: unknown required field {name!r}")

    def build(self, kind: str) -> Template:
        """Freeze into an immutable Template."""
        return Template(
            kind=kind, defaults=self.defaults, required=self.required, criteria=self.criteria
        )


def parse_template(kind: str, text: str) -> Template:
    """Parse template markdown (frontmatter only; body ignored)."""
    if kind not in TEMPLATE_FILES:
        raise ValueError(KIND_ERROR)
    allowed = set(FIELDS_BY_KIND[kind])
    lines = text.splitlines()
    try:
        fm = _frontmatter_lines(lines)
    except ValueError as exc:
        raise ValueError(f"template {kind}.md: {exc}") from exc
    state = _PartialTemplate(allowed=allowed)
    for lineno, raw in enumerate(fm, start=2):
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        state.apply_line(kind, raw, raw.strip(), lineno)
    state.validate(kind)
    return state.build(kind)


def load_template(kind: str, db_path: str | Path) -> Template:
    """Load a kind template for a DB (missing = empty/legacy; malformed raises)."""
    if kind not in TEMPLATE_FILES:
        raise ValueError(KIND_ERROR)
    d = templates_dir_for_db(db_path)
    if d is None:
        return Template(kind=kind)
    dest = d / TEMPLATE_FILES[kind]
    if not dest.is_file():
        return Template(kind=kind)
    try:
        text = dest.read_text()
    except OSError as exc:
        raise ValueError(f"template {kind}.md: cannot read ({exc})") from exc
    try:
        return parse_template(kind, text)
    except ValueError as exc:
        raise ValueError(f"{dest}: {exc}") from exc


def apply_template(kind: str, fields: dict[str, str], db_path: str | Path) -> dict[str, str]:
    """Fill empties from template defaults; enforce required (raises, names field)."""
    if kind not in FIELDS_BY_KIND:
        raise ValueError(KIND_ERROR)
    allowed = FIELDS_BY_KIND[kind]
    tmpl = load_template(kind, db_path)
    out = {k: fields.get(k, "") for k in allowed}
    for k in allowed:
        if not out[k] and tmpl.defaults.get(k):
            out[k] = tmpl.defaults[k]
    for name in tmpl.required:
        if not out.get(name, "").strip():
            flag = FLAG_BY_FIELD.get(name, name)
            raise ValueError(f"template {kind}.md requires '{name}' (empty) — pass {flag}")
    for name in ("why", "what", "desc"):
        if name in allowed:
            check_readable(kind, name, out.get(name, ""))
    return out


def template_criteria(kind: str, db_path: str | Path) -> list[str]:
    """Auto-add criteria for a kind (missing = none)."""
    return load_template(kind, db_path).criteria
