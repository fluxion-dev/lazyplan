"""Structured preview documents for the plan tree."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ...shared.design import (
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


def _header_row(status: str, label: str, oid: object, title: object) -> str:
    """One child header row: status glyph, kind and id, then the escaped title."""
    return _row(
        status_word(status, "plain"), _strong(f"{label}{oid}"), escape_markdown(str(title)), sep=" "
    )


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


def milestones_block(milestones: list[dict[str, Any]]) -> PreviewBlock | None:
    """Every milestone under the selected plan, as one header row."""
    if not milestones:
        return None
    lines = []
    for entry in milestones:
        milestone = entry.get("milestone", {})
        lines.append(
            _header_row(
                str(milestone.get("status", "")),
                "M",
                milestone.get("id"),
                milestone.get("title", ""),
            )
        )
    return PreviewBlock(f"milestones {len(milestones)}", tuple(lines))


def tasks_block(tasks: list[dict[str, Any]]) -> PreviewBlock | None:
    """Every task under the selected milestone, as one header row."""
    if not tasks:
        return None
    lines = [
        _header_row(str(task.get("status", "")), "T", task.get("id"), task.get("title", ""))
        for task in tasks
    ]
    return PreviewBlock(f"tasks {len(tasks)}", tuple(lines))


def notes_block(notes: list[dict[str, Any]]) -> PreviewBlock | None:
    if not notes:
        return None
    rows = []
    for note in notes[-3:]:
        text = str(note.get("text", "")).replace("\n", " ")
        rows.append(_row(f"@{escape_markdown(str(note.get('actor', '')))}", text, sep=" "))
    return PreviewBlock("notes", tuple(rows))


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


def acceptance_block(
    criteria: list[dict[str, Any]], *, detailed: bool = False
) -> PreviewBlock | None:
    """Acceptance criteria; plans show every item, other rows keep the short list."""
    if not criteria:
        return None
    done = sum(1 for criterion in criteria if criterion.get("done"))
    open_items = [criterion for criterion in criteria if not criterion.get("done")]
    tail = f" · {len(open_items)} open" if open_items else " · complete"
    if not detailed:
        return PreviewBlock(
            f"acceptance {done}/{len(criteria)}{tail}",
            tuple(
                _row(
                    "○",
                    criterion.get("text", ""),
                    _proof_chip(criterion.get("evidence")),
                    sep=" ",
                )
                for criterion in open_items[:3]
            ),
        )
    return PreviewBlock(
        f"acceptance {done}/{len(criteria)}{tail}",
        _detailed_acceptance_rows(criteria),
    )


def _detailed_acceptance_rows(criteria: list[dict[str, Any]]) -> tuple[str, ...]:
    """One row per criterion, open first, with its id and proof state."""
    ordered = sorted(
        criteria,
        key=lambda criterion: (bool(criterion.get("done")), int(criterion.get("id", 0) or 0)),
    )
    return tuple(
        _row(
            "✓" if criterion.get("done") else "○",
            _strong(f"C{criterion.get('id')}"),
            criterion.get("text", ""),
            f"· {_proof_chip(criterion.get('evidence'))}",
            sep=" ",
        )
        for criterion in ordered
    )


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
            _row(
                mark,
                _strong(f"C{criterion['id']}"),
                criterion.get("text", ""),
                f"{evidence.get('count', 0)} rows{exit_text}",
                escape_markdown(str(label)),
            )
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
    full: dict[str, Any], *, detailed_acceptance: bool = False
) -> tuple[PreviewBlock, ...]:
    """Coordination, acceptance, and provenance blocks for a preview."""
    blocks: list[PreviewBlock] = []
    notes = notes_block(full.get("notes", []))
    if notes is not None:
        blocks.append(notes)
    acceptance = acceptance_block(full.get("criteria", []), detailed=detailed_acceptance)
    if acceptance is not None:
        blocks.append(acceptance)
    links = full.get("effective_links") or full.get("links", [])
    forge = full.get("effective_forge_links") or full.get("forge_links", [])
    repos = full.get("effective_repos") or full.get("repos") or []
    source = _source_summary(links, forge, repos)
    if source is not None:
        blocks.append(source)
    return tuple(blocks)


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
    git_bits: list[str],
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
    blocks.extend(common_blocks(full, detailed_acceptance=True))
    return PreviewDocument(header, meta_line, tuple(blocks))


def build_milestone(
    store: PlanningPort,
    full: dict[str, Any],
    oid: int,
    git_bits: list[str],
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
    blocks.extend(common_blocks(full))
    return PreviewDocument(header, meta_line, tuple(blocks))


def build_task(
    store: PlanningPort,
    full: dict[str, Any],
    oid: int,
    git_bits: list[str],
) -> PreviewDocument:
    obj = full.get("task", {})
    header, meta_line = _title(store, "task", oid, obj, full)
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
    blocks.extend(common_blocks(full))
    return PreviewDocument(header, meta_line, tuple(blocks))


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
