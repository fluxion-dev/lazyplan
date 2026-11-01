"""Structured preview documents for the plan tree."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ...design import (
    KIND_ICON,
    SECTION_ICON,
    escape_markup,
    repo_project_name,
    status_word,
)

if TYPE_CHECKING:
    from ...store import Store


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
            key = block.heading.split(" ", 1)[0]
            icon = SECTION_ICON.get(key, "")
            prefix = f"[bold cyan]{icon}[/] " if icon else ""
            lines.append(f"{prefix}[bold]{escape_markup(block.heading)}[/]")
        lines.extend(block.lines)
    return lines


def _title(
    store: Store,
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


def acceptance_block(criteria: list[dict[str, Any]]) -> PreviewBlock | None:
    if not criteria:
        return None
    done = sum(1 for criterion in criteria if criterion.get("done"))
    open_items = [criterion for criterion in criteria if not criterion.get("done")]
    tail = f" · {len(open_items)} open" if open_items else " · complete"
    return PreviewBlock(
        f"acceptance {done}/{len(criteria)}{tail}",
        tuple(
            f"  [dim]○[/] {escape_markup(str(criterion.get('text', '')))}"
            for criterion in open_items[:3]
        ),
    )


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


def _meta_counts(kind: str, full: dict[str, Any]) -> list[str]:
    tasks = _tasks(kind, full)
    if not tasks:
        return []
    done = sum(1 for task in tasks if task.get("status") == "done")
    milestones = len(full.get("milestones", []))
    suffix = f" · {milestones} milestones" if kind == "plan" and milestones else ""
    return [f"[dim]{done}/{len(tasks)} tasks{suffix}[/]"]


def build_plan(
    store: Store,
    full: dict[str, Any],
    oid: int,
    git_bits: list[str],
) -> PreviewDocument:
    obj = full.get("plan", {})
    header, breadcrumb = _title(store, "plan", oid, obj)
    blocks: list[PreviewBlock] = []
    goal = str(obj.get("goal", "") or "").strip()
    desc = str(obj.get("description", "") or "").strip()
    if goal:
        blocks.append(PreviewBlock("why", (goal,)))
    if desc:
        blocks.append(PreviewBlock("what", (desc,)))
    next_tasks = next_block(_tasks("plan", full))
    if next_tasks is not None:
        blocks.append(next_tasks)
    blocks.extend(common_blocks(full, git_bits))
    return PreviewDocument(header, breadcrumb, tuple(_meta_counts("plan", full)), tuple(blocks))


def build_milestone(
    store: Store,
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
    next_tasks = next_block(_tasks("milestone", full))
    if next_tasks is not None:
        blocks.append(next_tasks)
    blocks.extend(common_blocks(full, git_bits))
    return PreviewDocument(
        header, breadcrumb, tuple(_meta_counts("milestone", full)), tuple(blocks)
    )


def build_task(
    store: Store,
    full: dict[str, Any],
    oid: int,
    git_bits: list[str],
) -> PreviewDocument:
    obj = full.get("task", {})
    header, breadcrumb = _title(store, "task", oid, obj)
    meta: list[str] = []
    if obj.get("blocked"):
        meta.append(f"[red]⚑ blocked[/] {escape_markup(str(obj.get('blocked_reason', '')))}")
    claim = obj.get("claim")
    if claim:
        meta.append(f"[dim]◉ claim @{escape_markup(str(claim.get('actor', '')))}[/]")
    blocks: list[PreviewBlock] = []
    desc = str(obj.get("description", "") or "").strip()
    if desc:
        blocks.append(PreviewBlock("details", (desc,)))
    task_notes = notes_block(obj.get("notes", []))
    if task_notes is not None:
        blocks.append(task_notes)
    blocks.extend(common_blocks(full, git_bits))
    return PreviewDocument(header, breadcrumb, tuple(meta), tuple(blocks))


def build_preview(
    store: Store,
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
