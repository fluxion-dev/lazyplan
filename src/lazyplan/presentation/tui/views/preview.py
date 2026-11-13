"""Structured preview documents for the plan tree."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ...shared.design import (
    escape_markdown,
    escape_markup,
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
    meta_line: str = ""
    blocks: tuple[PreviewBlock, ...] = ()
    footer: str = ""

    def render_head(self) -> str:
        """The sticky top: the title and one dim context line."""
        lines = [self.header]
        if self.meta_line:
            lines.append(self.meta_line)
        return "\n".join(lines)

    def render_markdown(self) -> str:
        """The scrollable body as deterministic Markdown."""
        lines: list[str] = []
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

    def render(self) -> str:
        """Render the whole document (head then body)."""
        head = self.render_head()
        body = self.render_markdown()
        return f"{head}\n{body}" if body else head


def _strong(label: object) -> str:
    """One escaped bold label for a generated row."""
    return f"**{escape_markdown(str(label))}**"


def _row(*parts: object, sep: str = " · ") -> str:
    """One Markdown list row with the given separator."""
    return "- " + sep.join(str(part) for part in parts if str(part))


HEADLINE_LIMIT = 120


def headline(text: str, limit: int = HEADLINE_LIMIT) -> str:
    """One paragraph collapsed to a single clamped line."""
    paragraph = text.strip().split("\n\n", 1)[0]
    line = " ".join(paragraph.split())
    if len(line) <= limit:
        return line
    cut = line[:limit].rsplit(" ", 1)[0].rstrip(" ,;:.-")
    return f"{cut}…"


def _child_row(letter: str, oid: object, title: object, suffix: str = "") -> str:
    """One plain child row: id, two spaces, title, then an optional count."""
    head = f"- {letter}{oid}  {escape_markdown(str(title))}"
    return f"{head} · {suffix}" if suffix else head


def _title(
    store: PlanningPort,
    kind: str,
    oid: int,
    obj: dict[str, Any],
    full: dict[str, Any],
) -> tuple[str, str]:
    """The title alone plus one dim line of ids, counts, and state."""
    title = str(obj.get("title", obj.get("name", "")))
    header = f"[bold]{escape_markup(title)}[/]"
    return header, _meta_line(store, kind, oid, obj, full)


def _done(rows: list[dict[str, Any]]) -> int:
    return sum(1 for row in rows if row.get("status") == "done" or row.get("done"))


def _meta_line(
    store: PlanningPort,
    kind: str,
    oid: int,
    obj: dict[str, Any],
    full: dict[str, Any],
) -> str:
    """One dim context line: ids, counts, and state for the selected level."""
    if kind == "plan":
        tasks = [task for entry in full.get("milestones", []) for task in entry.get("tasks", [])]
        criteria = full.get("criteria", [])
        parts = [f"P{oid}", f"{_done(tasks)}/{len(tasks)} tasks"]
        if criteria:
            parts.append(f"{_done(criteria)}/{len(criteria)} criteria")
    elif kind == "milestone":
        tasks = [entry.get("task", {}) for entry in full.get("tasks", [])]
        parts = [f"M{oid}", f"P{obj.get('plan_id')}", f"{_done(tasks)}/{len(tasks)} tasks"]
    else:
        parts = [f"T{oid}", f"M{obj.get('milestone_id')}", str(obj.get("status", ""))]
        if obj.get("blocked"):
            parts.append("blocked")
        claim = store.get_claim(oid)
        if claim is not None:
            parts.append(f"@{escape_markup(str(claim.actor))}")
    return "[dim]" + " · ".join(part for part in parts if part) + "[/]"


def _milestone_tasks(full: dict[str, Any]) -> list[dict[str, Any]]:
    """Flat task dicts for a milestone preview card."""
    return [entry.get("task", {}) for entry in full.get("tasks", [])]


def _task_states(tasks: list[dict[str, Any]]) -> str:
    """Compact done/total count for a task group."""
    done = sum(1 for task in tasks if task.get("status") == "done")
    return f"{done}/{len(tasks)}"


def milestones_block(milestones: list[dict[str, Any]]) -> PreviewBlock | None:
    """Every milestone under the selected plan, as one plain row."""
    if not milestones:
        return None
    lines = [
        _child_row(
            "M",
            entry.get("milestone", {}).get("id"),
            entry.get("milestone", {}).get("title", ""),
            _task_states(entry.get("tasks", [])),
        )
        for entry in milestones
    ]
    return PreviewBlock(f"milestones {len(milestones)}", tuple(lines))


def _task_state(task: dict[str, Any]) -> str:
    if task.get("blocked"):
        return "blocked"
    if task.get("status") == "doing":
        return "doing"
    return ""


def tasks_block(tasks: list[dict[str, Any]]) -> PreviewBlock | None:
    """Every task under the selected milestone, as one plain row."""
    if not tasks:
        return None
    lines = [
        _child_row("T", task.get("id"), task.get("title", ""), _task_state(task)) for task in tasks
    ]
    return PreviewBlock(f"tasks {len(tasks)}", tuple(lines))


def _proof_word(evidence: dict[str, Any] | None) -> str:
    """One plain word for a criterion's evidence state."""
    state = str((evidence or {}).get("state") or "none")
    if state == "pass":
        return "proven"
    if state == "fail":
        return "failing"
    return "no evidence"


def acceptance_block(
    criteria: list[dict[str, Any]], *, detailed: bool = False
) -> PreviewBlock | None:
    """Open acceptance criteria, or nothing when every item is done."""
    open_items = [criterion for criterion in criteria if not criterion.get("done")]
    if not open_items:
        return None
    done = len(criteria) - len(open_items)
    heading = f"acceptance {done}/{len(criteria)} · {len(open_items)} open"
    if not detailed:
        return PreviewBlock(
            heading,
            tuple(_row(str(criterion.get("text", ""))) for criterion in open_items[:3]),
        )
    rows = list(_detailed_acceptance_rows(open_items))
    if len(rows) > 3:
        rows = rows[:3] + [f"- {len(rows) - 3} more open"]
    return PreviewBlock(heading, tuple(rows))


def _detailed_acceptance_rows(criteria: list[dict[str, Any]]) -> tuple[str, ...]:
    """One plain row per open criterion."""
    ordered = sorted(criteria, key=lambda criterion: int(criterion.get("id", 0) or 0))
    return tuple(_row(str(criterion.get("text", ""))) for criterion in ordered)


def questions_block(questions: list[dict[str, Any]]) -> PreviewBlock | None:
    """Open questions on a plan."""
    open_items = [question for question in questions if question.get("status") == "open"]
    if not open_items:
        return None
    lines = [
        _row("?", _strong(f"Q{question['id']}"), question.get("text", ""), sep=" ")
        for question in open_items[:5]
    ]
    lines.append("- _c · questions hub_")
    return PreviewBlock(f"questions {len(open_items)} open", tuple(lines))


def proof_block(criteria: list[dict[str, Any]]) -> PreviewBlock | None:
    """Proof panel for the selected task: criterion, proof word, and evidence."""
    if not criteria:
        return None
    lines: list[str] = []
    for criterion in criteria[:5]:
        evidence = criterion.get("evidence") or {}
        latest = evidence.get("latest") or {}
        label = (
            latest.get("command")
            or latest.get("note")
            or str(latest.get("commit_sha", ""))[:12]
            or ""
        )
        parts = [
            str(criterion.get("text", "")),
            _proof_word(evidence),
        ]
        if label:
            parts.append(escape_markdown(str(label)))
        exit_code = latest.get("exit_code")
        if exit_code is not None:
            parts.append(f"exit {exit_code}")
        lines.append(_row(*parts))
    return PreviewBlock("proof", tuple(lines))


def approval_block(approval: dict[str, Any] | None) -> PreviewBlock | None:
    """Plan approval state: revision, actor, enforcement, and drift."""
    if not approval:
        return None
    revision = int(approval.get("revision", 0) or 0)
    if revision == 0:
        return None
    drift = int(approval.get("drift", 0) or 0)
    stamp = float(approval.get("approved_at", 0) or 0)
    day = time.strftime("%Y-%m-%d", time.localtime(stamp)) if stamp else "-"
    lines = [
        _row(
            f"r{revision}",
            day,
            f"@{escape_markdown(str(approval.get('actor', '')))}",
            "enforced" if approval.get("enforced") else "",
        )
    ]
    lines.append(_row("Δ", f"{drift} changes since approval") if drift else "- in sync")
    marks = {"add": "+", "edit": "~", "delete": "-"}
    for item in approval.get("recent") or []:
        action = marks.get(str(item.get("action") or ""), "?")
        field = escape_markdown(str(item.get("field") or ""))
        reason = str(item.get("reason") or "no reason")
        label = f"{item.get('kind')} {field}".strip()
        lines.append(_row(f"`{action}`", f"{label}: {reason}"))
    return PreviewBlock("approval", tuple(lines))


def worktrees_block(full: dict[str, Any]) -> PreviewBlock | None:
    """Read-only plan worktree registry, including the isolation requirement."""
    plan = full.get("plan") or {}
    rows = full.get("worktrees") or []
    required = bool(plan.get("worktree_required"))
    if not rows and not required:
        return None
    lines = [f"isolation {'required' if required else 'optional'}"]
    if not rows:
        lines.append("none registered")
    for row in rows:
        branch = escape_markdown(str(row.get("branch", "")))
        path = escape_markdown(str(row.get("worktree_path", "")))
        lines.append(f"`{branch}` -> {path}")
    return PreviewBlock("worktrees", tuple(lines))


def build_plan(
    store: PlanningPort,
    full: dict[str, Any],
    oid: int,
) -> PreviewDocument:
    obj = full.get("plan", {})
    header, meta_line = _title(store, "plan", oid, obj, full)
    blocks: list[PreviewBlock] = []
    questions = questions_block(full.get("questions", []))
    if questions is not None:
        blocks.append(questions)
    goal = str(obj.get("goal", "") or "").strip()
    desc = str(obj.get("description", "") or "").strip()
    lead = goal or desc
    if lead:
        blocks.append(PreviewBlock("why" if goal else "what", (headline(lead),)))
    approval = approval_block(full.get("approval"))
    if approval is not None:
        blocks.append(approval)
    worktrees = worktrees_block(full)
    if worktrees is not None:
        blocks.append(worktrees)
    refs = full.get("refs", [])
    if refs:
        blocks.append(PreviewBlock(f"references {len(refs)}", reference_lines(refs)))
    milestones = milestones_block(full.get("milestones", []))
    if milestones is not None:
        blocks.append(milestones)
    acceptance = acceptance_block(full.get("criteria", []), detailed=True)
    if acceptance is not None:
        blocks.append(acceptance)
    return PreviewDocument(header, meta_line, tuple(blocks))


def build_milestone(
    store: PlanningPort,
    full: dict[str, Any],
    oid: int,
) -> PreviewDocument:
    obj = full.get("milestone", {})
    header, meta_line = _title(store, "milestone", oid, obj, full)
    blocks: list[PreviewBlock] = []
    desc = str(obj.get("description", "") or "").strip()
    if desc:
        blocks.append(PreviewBlock("details", (headline(desc),)))
    tasks = tasks_block(_milestone_tasks(full))
    if tasks is not None:
        blocks.append(tasks)
    acceptance = acceptance_block(full.get("criteria", []))
    if acceptance is not None:
        blocks.append(acceptance)
    return PreviewDocument(header, meta_line, tuple(blocks))


def build_task(
    store: PlanningPort,
    full: dict[str, Any],
    oid: int,
) -> PreviewDocument:
    obj = full.get("task", {})
    header, meta_line = _title(store, "task", oid, obj, full)
    blocks: list[PreviewBlock] = []
    desc = str(obj.get("description", "") or "").strip()
    if desc:
        blocks.append(PreviewBlock("details", (desc,)))
    proof = proof_block(full.get("criteria", []))
    if proof is not None:
        blocks.append(proof)
    return PreviewDocument(header, meta_line, tuple(blocks))


def build_preview(
    store: PlanningPort,
    kind: str,
    oid: int,
    full: dict[str, Any],
) -> PreviewDocument:
    """Build the document for one selected row."""
    if kind == "plan":
        return build_plan(store, full, oid)
    if kind == "milestone":
        return build_milestone(store, full, oid)
    return build_task(store, full, oid)
