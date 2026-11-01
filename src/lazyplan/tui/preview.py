"""Textual app: preview."""

from __future__ import annotations

from typing import Any

try:
    from textual import events, on  # noqa: F401
    from textual.app import App, ComposeResult  # noqa: F401
    from textual.binding import Binding  # noqa: F401
    from textual.containers import Horizontal, Vertical, VerticalScroll  # noqa: F401
    from textual.reactive import reactive  # noqa: F401
    from textual.widgets import Label, Static, Tree  # noqa: F401
    from textual.widgets.tree import TreeNode  # noqa: F401

    from ..tree_nav import NavTree  # noqa: F401

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from ..design import (
    EMPTY_NO_PLANS,
    escape_markup,
    repo_project_name,
    status_word,
)
from ..messages import RowAction, SelectionChanged
from ..models import Status
from .base import AppBase

STATUS_CYCLE: list[Status | None] = [None, Status.TODO, Status.DOING, Status.DONE]
DOUBLE_CLICK_WINDOW = 0.5  # seconds between two clicks on one row


if _TEXTUAL_OK:

    class PreviewMixin(AppBase):
        """Preview behavior."""

        def _preview_milestone(self, full: dict[str, Any], oid: int) -> list[str]:
            obj = full.get("milestone", {})
            lines = self._preview_title("milestone", oid, obj)
            tasks = self._preview_tasks("milestone", full)
            if tasks:
                done = sum(1 for task in tasks if task.get("status") == "done")
                lines.append(f"[dim]{done}/{len(tasks)} tasks[/]")
            desc = str(obj.get("description", "") or "").strip()
            if desc:
                lines.extend(["", "[dim]details[/]", desc])
            open_tasks = [task for task in tasks if task.get("status") != "done"]
            if open_tasks:
                lines.extend(["", "[dim]next[/]"])
                for task in open_tasks[:3]:
                    lines.append(
                        f"  {status_word(str(task.get('status', '')), 'rich')} "
                        f"[dim]T{task.get('id')}[/] {escape_markup(str(task.get('title', '')))}"
                    )
            self._preview_common(lines, full)
            return lines

        def update_preview(self, force: bool = False) -> None:
            """Selection preview: a bounded summary, never the full plan."""
            try:
                body = self.query_one("#preview-body", Static)
            except Exception:
                return
            if not force and self.selected == self._preview_key:
                return
            self._preview_key = self.selected
            try:
                total_plans = self.store.counts()["plans"]
            except Exception:
                total_plans = 1
            if total_plans == 0:
                body.update(EMPTY_NO_PLANS)
                return
            if self.selected is None:
                body.update("select a plan (j/k or click) — enter opens it")
                return
            kind, oid = self.selected
            try:
                full = self.store.get_full(kind, oid)
            except Exception:
                body.update(f"{kind} {oid} — gone, press r")
                return
            if full is None:
                body.update(f"{kind} {oid} — gone, press r")
                return
            if kind == "plan":
                lines = self._preview_plan(full, oid)
            elif kind == "milestone":
                lines = self._preview_milestone(full, oid)
            else:
                lines = self._preview_task(full, oid)
            lines.extend(["", "[dim]enter open · e edit[/]"])
            body.update("\n".join(lines))

        def _preview_acceptance(self, lines: list[str], crits: list[dict]) -> None:
            if not crits:
                return
            crit_done = sum(1 for crit in crits if crit.get("done"))
            open_crits = [crit for crit in crits if not crit.get("done")]
            tail = f" · {len(open_crits)} open" if open_crits else " · complete"
            lines.extend(["", f"[dim]acceptance {crit_done}/{len(crits)}{tail}[/]"])
            for crit in open_crits[:3]:
                lines.append(f"  · {escape_markup(str(crit.get('text', '')))}")

        def _preview_source_summary(
            self,
            lines: list[str],
            links: list[dict],
            forge: list[dict],
            repos: list[dict],
        ) -> None:
            if links or forge or repos:
                bits = []
                if links:
                    bits.append(f"{len(links)} commits")
                if forge:
                    bits.append(f"{len(forge)} PRs")
                if repos:
                    names = [name for name in (repo_project_name(r) for r in repos) if name]
                    bits.append(
                        "repos: " + ", ".join(names[:3]) if names else f"{len(repos)} repos"
                    )
                lines.append(f"[dim]{' · '.join(bits)}[/]")
            if not links:
                return
            newest = max(links, key=lambda link: int(link.get("timestamp", 0) or 0))
            files = len({path for link in links for path in link.get("files", [])})
            stale = sum(1 for link in links if link.get("stale"))
            last = (
                f"last {str(newest.get('sha', ''))[:12]} "
                f"{escape_markup(str(newest.get('subject', '') or '(no subject)'))}"
            )
            if files:
                last += f" · {files} files"
            if stale:
                last += f" · {stale} stale"
            lines.append(f"[dim]{last}[/]")

        def _on_row_action(self, e: RowAction) -> None:
            """Custom intents bubble here; App owns the side effects."""
            if e.action == "toggle-status":
                self.action_toggle_status()
            elif e.action == "open-detail":
                if e.kind is not None and e.oid is not None:
                    self._open_detail(e.kind, e.oid)
                else:
                    self.action_open_detail()
            elif e.action == "fold-all":
                self.action_fold_all()
            elif e.action == "detail-saved":
                self._saved("saved detail")
            e.stop()

        def _preview_common(self, lines: list[str], full: dict[str, Any]) -> None:
            self._preview_notes(lines, full.get("notes", []))
            self._preview_acceptance(lines, full.get("criteria", []))
            links = full.get("effective_links") or full.get("links", [])
            forge = full.get("effective_forge_links") or full.get("forge_links", [])
            repos = full.get("effective_repos") or full.get("repos") or []
            self._preview_source_summary(lines, links, forge, repos)
            git_bits = self.git_state_controller.preview_bits(repos)
            if git_bits:
                lines.append(f"[dim]git: {' · '.join(git_bits)}[/]")

        def _preview_title(self, kind: str, oid: int, obj: dict[str, Any]) -> list[str]:
            title = str(obj.get("title", obj.get("name", "")))
            status = str(obj.get("status", ""))
            label = {"plan": "P", "milestone": "M", "task": "T"}[kind]
            lines = [
                f"{status_word(status, 'rich')} "
                f"[dim]{label}{oid}[/] [bold]{escape_markup(title)}[/]"
            ]
            if kind == "milestone":
                lines.append(f"[dim]P{obj.get('plan_id')} › M{oid}[/]")
            elif kind == "task":
                milestone = self.store.get_milestone(int(obj.get("milestone_id", 0)))
                plan_id = milestone.plan_id if milestone else "?"
                lines.append(f"[dim]P{plan_id} › M{obj.get('milestone_id')} › T{oid}[/]")
            return lines

        def _preview_tasks(self, kind: str, full: dict[str, Any]) -> list[dict[str, Any]]:
            """Flat task dicts for a preview card (plan/milestone/task)."""
            if kind == "plan":
                return [
                    task for entry in full.get("milestones", []) for task in entry.get("tasks", [])
                ]
            if kind == "milestone":
                return [entry.get("task", {}) for entry in full.get("tasks", [])]
            return [full.get("task", {})]

        def _on_selection_changed(self, e: SelectionChanged) -> None:
            """Custom message (bubbles FoldTree -> App): track cursor."""
            self.selected = (e.kind, e.oid)
            self.update_preview()

        def _preview_notes(self, lines: list[str], notes: list[dict[str, Any]]) -> None:
            """Show the latest handoff notes."""
            if not notes:
                return
            lines.extend(["", "[dim]notes[/]"])
            for note in notes[-3:]:
                lines.append(
                    f"  [dim]@{escape_markup(str(note.get('actor', '')))}[/] "
                    f"{escape_markup(str(note.get('text', '')))}"
                )

        def _preview_plan(self, full: dict[str, Any], oid: int) -> list[str]:
            obj = full.get("plan", {})
            lines = self._preview_title("plan", oid, obj)
            tasks = self._preview_tasks("plan", full)
            milestones = full.get("milestones", [])
            if tasks:
                done = sum(1 for task in tasks if task.get("status") == "done")
                lines.append(f"[dim]{done}/{len(tasks)} tasks · {len(milestones)} milestones[/]")
            goal = str(obj.get("goal", "") or "").strip()
            desc = str(obj.get("description", "") or "").strip()
            if goal:
                lines.extend(["", "[dim]why[/]", goal])
            if desc:
                lines.extend(["", "[dim]what[/]", desc])
            open_tasks = [task for task in tasks if task.get("status") != "done"]
            if open_tasks:
                lines.extend(["", "[dim]next[/]"])
                for task in open_tasks[:3]:
                    lines.append(
                        f"  {status_word(str(task.get('status', '')), 'rich')} "
                        f"[dim]T{task.get('id')}[/] {escape_markup(str(task.get('title', '')))}"
                    )
            self._preview_common(lines, full)
            return lines

        def _preview_task(self, full: dict[str, Any], oid: int) -> list[str]:
            obj = full.get("task", {})
            lines = self._preview_title("task", oid, obj)
            if obj.get("blocked"):
                lines.append(f"[red]blocked[/] {escape_markup(str(obj.get('blocked_reason', '')))}")
            claim = obj.get("claim")
            if claim:
                lines.append(f"[dim]claim @{escape_markup(str(claim.get('actor', '')))}[/]")
            desc = str(obj.get("description", "") or "").strip()
            if desc:
                lines.extend(["", "[dim]details[/]", desc])
            self._preview_notes(lines, obj.get("notes", []))
            self._preview_common(lines, full)
            return lines
