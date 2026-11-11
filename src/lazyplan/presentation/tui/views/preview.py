"""Structured preview documents for the plan tree."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ...shared.design import (
    KIND_ICON,
    SECTION_ICON,
    escape_markdown,
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

    def render_markdown(self) -> str:
        """The scrollable body as deterministic Markdown."""
        lines = list(self.meta)
        for block in self.blocks:
            if lines and lines[-1] != "":
                lines.append("")
            if block.heading:
                lines.append(f"## {block.heading.upper()}")
            body = list(block.lines)
            while body and not body[0].strip():
                body.pop(0)
            while body and not body[-1].strip():
                body.pop()
            lines.extend(body)
        if self.footer:
            if lines and lines[-1] != "":
                lines.append("")
            lines.extend(self.footer.splitlines())
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        return "\n".join(lines)

    def render_body(self, width: int | None = None) -> str:
        """The scrollable body; `width` is accepted for older callers."""
        _ = width
        return self.render_markdown()

    def render(self, width: int | None = None) -> str:
        """Render the whole document (head then body)."""
        head = self.render_head()
        body = self.render_body(width)
        return f"{head}\n{body}" if body else head


def render_heading(heading: str, width: int | None) -> str:
    """A bold heading, or a full-width tinted bar when width is known."""
    text = heading.upper()
    escaped = escape_markup(text)
    if width is None or width <= 0:
        return f"[bold]{escaped}[/]"
    label = f" {text} "
    if len(label) > width:
        label = label[:width]
    padding = " " * (width - len(label))
    return f"[on $lp-surface-raised]{escape_markup(label)}{padding}[/]"


def normalize_lines(lines: list[str]) -> list[str]:
    """Collapse repeated blanks and strip leading or trailing blank rows."""
    out: list[str] = []
    for line in lines:
        if not line.strip():
            if out and out[-1] != "":
                out.append("")
            continue
        out.append(line)
    while out and out[0] == "":
        out.pop(0)
    while out and out[-1] == "":
        out.pop()
    return out


def _block_lines(block: PreviewBlock, width: int | None) -> list[str]:
    """One block's heading and body with any leading blank rows removed."""
    lines: list[str] = []
    if block.heading:
        lines.append(render_heading(block.heading, width))
    body = list(block.lines)
    while body and not body[0].strip():
        body.pop(0)
    lines.extend(body)
    return lines


def render_blocks(blocks: tuple[PreviewBlock, ...], width: int | None = None) -> list[str]:
    """Render blocks with one blank line before each heading."""
    lines: list[str] = []
    for block in blocks:
        lines.append("")
        lines.extend(_block_lines(block, width))
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
    """Every milestone under the selected plan, as a title-only row."""
    if not milestones:
        return None
    lines: list[str] = []
    for entry in milestones:
        milestone = entry.get("milestone", {})
        title = str(milestone.get("title", ""))
        lines.append(f"- **{escape_markdown(title)}**")
    return PreviewBlock(f"milestones {len(milestones)}", tuple(lines))


def tasks_block(tasks: list[dict[str, Any]]) -> PreviewBlock | None:
    """Every task under the selected milestone, with its description."""
    if not tasks:
        return None
    lines: list[str] = []
    for task in tasks:
        claim = task.get("claim") if isinstance(task.get("claim"), dict) else None
        claim_text = f" · @{escape_markdown(str(claim.get('actor', '')))}" if claim else ""
        blocked = " · blocked" if task.get("blocked") else ""
        lines.append(
            f"- {status_word(str(task.get('status', '')), 'plain')} "
            f"**T{task.get('id')}** {escape_markdown(str(task.get('title', '')))}{blocked}{claim_text}"
        )
        desc = str(task.get("description", "") or "").strip()
        for line in desc.splitlines():
            lines.append(f"  {line}" if line.strip() else "")
    return PreviewBlock(f"tasks {len(tasks)}", tuple(lines))


def next_block(tasks: list[dict[str, Any]]) -> PreviewBlock | None:
    """The first three open tasks."""
    open_tasks = [task for task in tasks if task.get("status") != "done"]
    if not open_tasks:
        return None
    return PreviewBlock(
        "next",
        tuple(
            f"- {status_word(str(task.get('status', '')), 'plain')} "
            f"**T{task.get('id')}** {escape_markdown(str(task.get('title', '')))}"
            for task in open_tasks[:3]
        ),
    )


def notes_block(notes: list[dict[str, Any]]) -> PreviewBlock | None:
    if not notes:
        return None
    return PreviewBlock(
        "notes",
        tuple(
            f"- @{escape_markdown(str(note.get('actor', '')))} "
            f"{str(note.get('text', '')).replace(chr(10), ' ')}"
            for note in notes[-3:]
        ),
    )


def _proof_chip(evidence: dict[str, Any] | None) -> str:
    """One compact state chip for a criterion's evidence."""
    data = evidence or {}
    state = str(data.get("state") or "none")
    count = int(data.get("count", 0) or 0)
    if state == "pass":
        return f"✓ {count}"
    if state == "fail":
        return f"✗ {count}"
    return "—"


def acceptance_block(criteria: list[dict[str, Any]]) -> PreviewBlock | None:
    if not criteria:
        return None
    done = sum(1 for criterion in criteria if criterion.get("done"))
    open_items = [criterion for criterion in criteria if not criterion.get("done")]
    tail = f" · {len(open_items)} open" if open_items else " · complete"
    return PreviewBlock(
        f"acceptance {done}/{len(criteria)}{tail}",
        tuple(
            f"- ○ {criterion.get('text', '')} {_proof_chip(criterion.get('evidence'))}"
            for criterion in open_items[:3]
        ),
    )


def questions_block(questions: list[dict[str, Any]]) -> PreviewBlock | None:
    """Open questions on a plan."""
    open_items = [question for question in questions if question.get("status") == "open"]
    if not open_items:
        return None
    lines = [f"- ? **Q{question['id']}** {question.get('text', '')}" for question in open_items[:5]]
    lines.append("- _c · questions hub_")
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
        mark = "✓" if state == "pass" else "✗" if state == "fail" else "—"
        label = (
            latest.get("command")
            or latest.get("note")
            or str(latest.get("commit_sha", ""))[:12]
            or "-"
        )
        exit_code = latest.get("exit_code")
        exit_text = f" exit {exit_code}" if exit_code is not None else ""
        lines.append(
            f"- {mark} **C{criterion['id']}** {criterion.get('text', '')} · "
            f"{evidence.get('count', 0)} rows{exit_text} · {escape_markdown(str(label))}"
        )
    return PreviewBlock("proof", tuple(lines))


def approval_block(approval: dict[str, Any] | None) -> PreviewBlock | None:
    """Plan approval state: revision, actor, enforcement, and drift."""
    if not approval:
        return None
    revision = int(approval.get("revision", 0) or 0)
    if revision == 0:
        return PreviewBlock("approval", ("- no approved revision",))
    drift = int(approval.get("drift", 0) or 0)
    enforced = " · enforced" if approval.get("enforced") else ""
    stamp = float(approval.get("approved_at", 0) or 0)
    day = time.strftime("%Y-%m-%d", time.localtime(stamp)) if stamp else "-"
    lines = [f"- r{revision} {day} @{escape_markdown(str(approval.get('actor', '')))}{enforced}"]
    if drift:
        lines.append(f"- Δ {drift} changes since approval")
    else:
        lines.append("- in sync")
    marks = {"add": "+", "edit": "~", "delete": "-"}
    for item in approval.get("recent") or []:
        action = marks.get(str(item.get("action") or ""), "?")
        field = str(item.get("field") or "")
        suffix = f" {escape_markdown(field)}" if field else ""
        reason = str(item.get("reason") or "no reason")
        lines.append(f"- {action} {item.get('kind')}{suffix}: {reason}")
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
        rendered = ", ".join(escape_markdown(name) for name in names[:3])
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
    return PreviewBlock("source", (bits,))


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
