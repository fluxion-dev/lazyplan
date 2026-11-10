"""Structured preview documents for the plan tree."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ...shared.design import (
    KIND_ICON,
    SECTION_ICON,
    escape_markup,
    repo_project_name,
    status_word,
)
from .reference_lines import reference_lines

if TYPE_CHECKING:
    from ....core.ports.planning import PlanningPort


@dataclass(frozen=True)
class PreviewBlock:
    """One preview section: an optional heading and its lines."""

    heading: str
    lines: tuple[str, ...]


@dataclass(frozen=True)
class PreviewDocument:
    """Everything the preview panel renders for one selection."""

    header: str
    breadcrumb: str = ""
    meta: tuple[str, ...] = ()
    blocks: tuple[PreviewBlock, ...] = ()
    footer: str = ""

    def render_head(self) -> str:
        """The sticky top: status, title, and breadcrumb."""
        lines = [self.header]
        if self.breadcrumb:
            lines.append(self.breadcrumb)
        return "\n".join(lines)

    def render_body(self) -> str:
        """The scrollable body: meta chips, sections, and optional footer."""
        lines = list(self.meta)
        lines.extend(render_blocks(self.blocks))
        if self.footer:
            lines.extend(["", self.footer])
        return "\n".join(lines).lstrip("\n")

    def render(self) -> str:
        """Render the whole document (head then body)."""
        head = self.render_head()
        body = self.render_body()
        return f"{head}\n{body}" if body else head


def render_blocks(blocks: tuple[PreviewBlock, ...]) -> list[str]:
    """Render blocks with the one blank line and heading grammar."""
    lines: list[str] = []
    for block in blocks:
        lines.append("")
        if block.heading:
            lines.append(f"[bold]{escape_markup(block.heading.upper())}[/]")
        lines.extend(block.lines)
    return lines


def _title(
    store: PlanningPort,
    kind: str,
    oid: int,
    obj: dict[str, Any],
) -> tuple[str, str]:
    title = str(obj.get("title", obj.get("name", "")))
    status = str(obj.get("status", ""))
    label = {"plan": "P", "milestone": "M", "task": "T"}[kind]
    icon = KIND_ICON[kind]
    header = (
        f"{status_word(status, 'rich')} "
        f"[bold cyan]{icon} {label}{oid}[/] [bold]{escape_markup(title)}[/]"
    )
    breadcrumb = ""
    if kind == "milestone":
        breadcrumb = f"[dim]◈ P{obj.get('plan_id')} › ◇ M{oid}[/]"
    elif kind == "task":
        milestone = store.get_milestone(int(obj.get("milestone_id", 0)))
        plan_id = milestone.plan_id if milestone else "?"
        breadcrumb = f"[dim]◈ P{plan_id} › ◇ M{obj.get('milestone_id')} › ▹ T{oid}[/]"
    return header, breadcrumb


def _tasks(kind: str, full: dict[str, Any]) -> list[dict[str, Any]]:
    """Flat task dicts for a preview card (plan/milestone/task)."""
    if kind == "plan":
        return [task for entry in full.get("milestones", []) for task in entry.get("tasks", [])]
    if kind == "milestone":
        return [entry.get("task", {}) for entry in full.get("tasks", [])]
    return [full.get("task", {})]


def milestones_block(milestones: list[dict[str, Any]]) -> PreviewBlock | None:
    """Every milestone under the selected plan, with its description."""
    if not milestones:
        return None
    lines: list[str] = []
    for entry in milestones:
        milestone = entry.get("milestone", {})
        tasks = entry.get("tasks", [])
        done = sum(1 for task in tasks if task.get("status") == "done")
        progress = f" · {done}/{len(tasks)} tasks" if tasks else ""
        lines.append(
            f"  {status_word(str(milestone.get('status', '')), 'rich')} "
            f"[dim]◇ M{milestone.get('id')}[/] "
            f"{escape_markup(str(milestone.get('title', '')))}"
            f"[dim]{progress}[/]"
        )
        desc = str(milestone.get("description", "") or "").strip()
        for line in desc.splitlines():
            if line.strip():
                lines.append(f"    [dim]{escape_markup(line.strip())}[/]")
    return PreviewBlock(f"milestones {len(milestones)}", tuple(lines))


def tasks_block(tasks: list[dict[str, Any]]) -> PreviewBlock | None:
    """Every task under the selected milestone, with its description."""
    if not tasks:
        return None
    lines: list[str] = []
    for task in tasks:
        claim = task.get("claim") if isinstance(task.get("claim"), dict) else None
        claim_text = f" [dim]@{escape_markup(str(claim.get('actor', '')))}[/]" if claim else ""
        blocked = " [red]⚑[/]" if task.get("blocked") else ""
        lines.append(
            f"  {status_word(str(task.get('status', '')), 'rich')} "
            f"[dim]▹ T{task.get('id')}[/] "
            f"{escape_markup(str(task.get('title', '')))}{blocked}{claim_text}"
        )
        desc = str(task.get("description", "") or "").strip()
        for line in desc.splitlines():
            if line.strip():
                lines.append(f"    [dim]{escape_markup(line.strip())}[/]")
    return PreviewBlock(f"tasks {len(tasks)}", tuple(lines))


def next_block(tasks: list[dict[str, Any]]) -> PreviewBlock | None:
    """The first three open tasks."""
    open_tasks = [task for task in tasks if task.get("status") != "done"]
    if not open_tasks:
        return None
    return PreviewBlock(
        "next",
        tuple(
            f"  {status_word(str(task.get('status', '')), 'rich')} "
            f"[dim]▹ T{task.get('id')}[/] {escape_markup(str(task.get('title', '')))}"
            for task in open_tasks[:3]
        ),
    )


def notes_block(notes: list[dict[str, Any]]) -> PreviewBlock | None:
    if not notes:
        return None
    return PreviewBlock(
        "notes",
        tuple(
            f"  [dim]@{escape_markup(str(note.get('actor', '')))}[/] "
            f"{escape_markup(str(note.get('text', '')))}"
            for note in notes[-3:]
        ),
    )


def _proof_chip(evidence: dict[str, Any] | None) -> str:
    """One compact state chip for a criterion's evidence."""
    data = evidence or {}
    state = str(data.get("state") or "none")
    count = int(data.get("count", 0) or 0)
    if state == "pass":
        return f"[green]✓ {count}[/]"
    if state == "fail":
        return f"[red]✗ {count}[/]"
    return "[dim]—[/]"


def acceptance_block(criteria: list[dict[str, Any]]) -> PreviewBlock | None:
    if not criteria:
        return None
    done = sum(1 for criterion in criteria if criterion.get("done"))
    open_items = [criterion for criterion in criteria if not criterion.get("done")]
    tail = f" · {len(open_items)} open" if open_items else " · complete"
    return PreviewBlock(
        f"acceptance {done}/{len(criteria)}{tail}",
        tuple(
            f"  [dim]○[/] {escape_markup(str(criterion.get('text', '')))} "
            f"{_proof_chip(criterion.get('evidence'))}"
            for criterion in open_items[:3]
        ),
    )


def questions_block(questions: list[dict[str, Any]]) -> PreviewBlock | None:
    """Open questions on a plan."""
    open_items = [question for question in questions if question.get("status") == "open"]
    if not open_items:
        return None
    lines = [
        f"  [yellow]?[/] [dim]Q{question['id']}[/] {escape_markup(str(question.get('text', '')))}"
        for question in open_items[:5]
    ]
    lines.append("  [dim]c · questions hub[/]")
    return PreviewBlock(f"questions {len(open_items)} open", tuple(lines))


def proof_block(criteria: list[dict[str, Any]]) -> PreviewBlock | None:
    """Proof panel for the selected task."""
    if not criteria:
        return None
    lines: list[str] = []
    for criterion in criteria[:5]:
        evidence = criterion.get("evidence") or {}
        latest = evidence.get("latest") or {}
        state = str(evidence.get("state") or "none")
        mark = "[green]✓[/]" if state == "pass" else "[red]✗[/]" if state == "fail" else "[dim]—[/]"
        label = (
            latest.get("command")
            or latest.get("note")
            or str(latest.get("commit_sha", ""))[:12]
            or "-"
        )
        exit_code = latest.get("exit_code")
        exit_text = f" exit {exit_code}" if exit_code is not None else ""
        lines.append(
            f"  {mark} [dim]#{criterion['id']}[/] "
            f"{escape_markup(str(criterion.get('text', '')))} · "
            f"{evidence.get('count', 0)} rows{exit_text} · {escape_markup(str(label))}"
        )
    return PreviewBlock("proof", tuple(lines))


def approval_block(approval: dict[str, Any] | None) -> PreviewBlock | None:
    """Plan approval state: revision, actor, enforcement, and drift."""
    if not approval:
        return None
    revision = int(approval.get("revision", 0) or 0)
    if revision == 0:
        return PreviewBlock("approval", ("  no approved revision",))
    drift = int(approval.get("drift", 0) or 0)
    enforced = " · enforced" if approval.get("enforced") else ""
    stamp = float(approval.get("approved_at", 0) or 0)
    day = time.strftime("%Y-%m-%d", time.localtime(stamp)) if stamp else "-"
    lines = [f"  r{revision} {day} @{escape_markup(str(approval.get('actor', '')))}{enforced}"]
    if drift:
        lines.append(f"  [yellow]Δ[/] {drift} changes since approval")
    else:
        lines.append("  in sync")
    marks = {"add": "+", "edit": "~", "delete": "-"}
    for item in approval.get("recent") or []:
        action = marks.get(str(item.get("action") or ""), "?")
        field = str(item.get("field") or "")
        suffix = f" {field}" if field else ""
        reason = escape_markup(str(item.get("reason") or "no reason"))
        lines.append(f"  {action} {item.get('kind')}{suffix}: {reason}")
    return PreviewBlock("approval", tuple(lines))


def _source_bits(
    links: list[dict[str, Any]],
    forge: list[dict[str, Any]],
    repos: list[dict[str, Any]],
) -> str:
    bits: list[str] = []
    if links:
        bits.append(f"{len(links)} commits")
    if forge:
        bits.append(f"{len(forge)} PRs")
    if repos:
        names = [name for name in (repo_project_name(repo) for repo in repos) if name]
        rendered = ", ".join(escape_markup(name) for name in names[:3])
        bits.append("repos: " + rendered if names else f"{len(repos)} repos")
    return " · ".join(bits)


def _source_summary(
    links: list[dict[str, Any]],
    forge: list[dict[str, Any]],
    repos: list[dict[str, Any]],
) -> PreviewBlock | None:
    bits = _source_bits(links, forge, repos)
    if not bits:
        return None
    return PreviewBlock("source", (f"[dim]{bits}[/]",))


def common_blocks(
    full: dict[str, Any],
    git_bits: list[str],
) -> tuple[PreviewBlock, ...]:
    """Coordination, acceptance, and provenance blocks for a preview."""
    blocks: list[PreviewBlock] = []
    notes = notes_block(full.get("notes", []))
    if notes is not None:
        blocks.append(notes)
    acceptance = acceptance_block(full.get("criteria", []))
    if acceptance is not None:
        blocks.append(acceptance)
    links = full.get("effective_links") or full.get("links", [])
    forge = full.get("effective_forge_links") or full.get("forge_links", [])
    repos = full.get("effective_repos") or full.get("repos") or []
    source = _source_summary(links, forge, repos)
    if source is not None:
        blocks.append(source)
    return tuple(blocks)


def common_lines(full: dict[str, Any], git_bits: list[str]) -> list[str]:
    """Render the common blocks for callers that still need plain lines."""
    lines = render_blocks(common_blocks(full, git_bits))
    if git_bits:
        lines.extend(["", f"[dim]{SECTION_ICON['git']} git: {' · '.join(git_bits)}[/]"])
    return lines


def build_plan(
    store: PlanningPort,
    full: dict[str, Any],
    oid: int,
    git_bits: list[str],
) -> PreviewDocument:
    obj = full.get("plan", {})
    header, breadcrumb = _title(store, "plan", oid, obj)
    blocks: list[PreviewBlock] = []
    questions = questions_block(full.get("questions", []))
    if questions is not None:
        blocks.append(questions)
    goal = str(obj.get("goal", "") or "").strip()
    desc = str(obj.get("description", "") or "").strip()
    if goal:
        blocks.append(PreviewBlock("why", (goal,)))
    if desc:
        blocks.append(PreviewBlock("what", (desc,)))
    approval = approval_block(full.get("approval"))
    if approval is not None:
        blocks.append(approval)
    refs = full.get("refs", [])
    if refs:
        blocks.append(PreviewBlock(f"references {len(refs)}", reference_lines(refs)))
    milestones = milestones_block(full.get("milestones", []))
    if milestones is not None:
        blocks.append(milestones)
    next_tasks = next_block(_tasks("plan", full))
    if next_tasks is not None:
        blocks.append(next_tasks)
    blocks.extend(common_blocks(full, git_bits))
    return PreviewDocument(header, breadcrumb, (), tuple(blocks))


def build_milestone(
    store: PlanningPort,
    full: dict[str, Any],
    oid: int,
    git_bits: list[str],
) -> PreviewDocument:
    obj = full.get("milestone", {})
    header, breadcrumb = _title(store, "milestone", oid, obj)
    blocks: list[PreviewBlock] = []
    desc = str(obj.get("description", "") or "").strip()
    if desc:
        blocks.append(PreviewBlock("details", (desc,)))
    tasks = tasks_block(_tasks("milestone", full))
    if tasks is not None:
        blocks.append(tasks)
    blocks.extend(common_blocks(full, git_bits))
    return PreviewDocument(header, breadcrumb, (), tuple(blocks))


def build_task(
    store: PlanningPort,
    full: dict[str, Any],
    oid: int,
    git_bits: list[str],
) -> PreviewDocument:
    obj = full.get("task", {})
    header, breadcrumb = _title(store, "task", oid, obj)
    blocks: list[PreviewBlock] = []
    desc = str(obj.get("description", "") or "").strip()
    if desc:
        blocks.append(PreviewBlock("details", (desc,)))
    task_notes = notes_block(obj.get("notes", []))
    if task_notes is not None:
        blocks.append(task_notes)
    proof = proof_block(full.get("criteria", []))
    if proof is not None:
        blocks.append(proof)
    blocks.extend(common_blocks(full, git_bits))
    return PreviewDocument(header, breadcrumb, (), tuple(blocks))


def build_preview(
    store: PlanningPort,
    kind: str,
    oid: int,
    full: dict[str, Any],
    git_bits: list[str],
) -> PreviewDocument:
    """Build the document for one selected row."""
    if kind == "plan":
        return build_plan(store, full, oid, git_bits)
    if kind == "milestone":
        return build_milestone(store, full, oid, git_bits)
    return build_task(store, full, oid, git_bits)
