"""TUI screens: modal forms and detail views.

The app shell (LazyplanApp) lives in tui.py; every overlay lives here.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

try:
    from textual import on  # noqa: F401
    from textual.app import ComposeResult  # noqa: F401
    from textual.binding import Binding  # noqa: F401
    from textual.containers import Horizontal, Vertical, VerticalScroll  # noqa: F401
    from textual.screen import ModalScreen, Screen  # noqa: F401
    from textual.widgets import (  # noqa: F401
        Button,
        Input,
        Label,
        OptionList,
        Static,
        TextArea,
    )
    from textual.widgets.option_list import Option  # noqa: F401

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from ... import services
from ...design import escape_markup, msg_error, status_word
from ...render import render_commits, render_forge_links
from ...source import SourceTrail, build_source_trail
from ...templates import load_template
from ...vcs import commit_url, detect_backend, origin_url

if TYPE_CHECKING:
    from ...store import Store
from .base import _row
from .forms import ConfirmScreen, FilterPromptScreen, NewMilestoneScreen, NewTaskScreen

if _TEXTUAL_OK:

    class DetailScreen(Screen):
        """Read-first detail page; `e` switches to an in-place edit form."""

        BINDINGS = [
            Binding("escape", "back", "Back", priority=True),
            Binding("e", "toggle_edit", "Edit"),
            Binding("s", "advance_status", "Status"),
            Binding("x", "tick_criterion", "Tick"),
            Binding("a", "add_criterion", "Criterion"),
            Binding("n", "add_child", "New child"),
            Binding("d", "delete_row", "Delete"),
            Binding("g", "open_source", "Source"),
            Binding("ctrl+s", "save", "Save", priority=True),
        ]

        def __init__(self, store: Store, kind: str, oid: int, edit: bool = False) -> None:
            super().__init__()
            self._dstore = store
            self.dkind, self.doid = kind, oid
            self._editing = edit
            self._snapshot: tuple[str, ...] | None = None
            self._full: dict[str, Any] = {}
            self._trail: SourceTrail | None = None

        def compose(self) -> ComposeResult:
            with Vertical(id="detail-page"):
                yield Static("", id="detail-head")
                with VerticalScroll(id="detail-read"):
                    yield Static("", id="detail-body")
                with VerticalScroll(id="detail-edit"):
                    yield Label("Title")
                    yield Input(placeholder="title", id="d-title")
                    if self.dkind == "plan":
                        yield Label("Why")
                        yield Input(placeholder="why does this exist?", id="d-why")
                        yield Label("What")
                    else:
                        yield Label("Details")
                    yield TextArea(id="d-desc")
                    with _row():
                        yield Button("Save", id="ok", variant="primary")
                        yield Button("Cancel", id="cancel")
                yield Label("", id="detail-hints")

        def on_mount(self) -> None:
            if not self._load():
                return
            self._show_mode()
            self._render_read()
            if self._editing:
                self._snapshot = self._form_snapshot()
                self.query_one("#d-title", Input).focus()
            else:
                self.query_one("#detail-read", VerticalScroll).focus()

        def _load(self) -> bool:
            full = self._dstore.get_full(self.dkind, self.doid)
            if full is None:
                self.dismiss(None)
                return False
            self._full = full
            self._trail = build_source_trail(self._dstore, self.dkind, self.doid)
            obj = self._obj()
            title = str(obj.get("title", obj.get("name", "")))
            desc = str(obj.get("description", "") or "")
            self.query_one("#d-title", Input).value = title
            self.query_one("#d-desc", TextArea).text = desc
            if self.dkind == "plan":
                self.query_one("#d-why", Input).value = str(obj.get("goal", "") or "")
            return True

        def _obj(self) -> dict[str, Any]:
            key = {"plan": "plan", "milestone": "milestone", "task": "task"}[self.dkind]
            return dict(self._full.get(key, {}))

        def _breadcrumb(self) -> str:
            if self.dkind == "plan":
                return f"P{self.doid}"
            if self.dkind == "milestone":
                return f"P{self._obj().get('plan_id')} › M{self.doid}"
            task = self._obj()
            milestone = self._dstore.get_milestone(int(task.get("milestone_id", 0)))
            plan_id = milestone.plan_id if milestone else "?"
            return f"P{plan_id} › M{task.get('milestone_id')} › T{self.doid}"

        def _read_text(self, lines: list[str], obj: dict[str, Any]) -> None:
            """Why/what for plans; details for milestones and tasks."""
            desc = str(obj.get("description", "") or "").strip()
            goal = str(obj.get("goal", "") or "").strip() if self.dkind == "plan" else ""
            if goal:
                lines.extend(["", "[dim]why[/]", goal])
            if desc:
                heading = "[dim]what[/]" if self.dkind == "plan" else "[dim]details[/]"
                lines.extend(["", heading, desc])

        def _read_coordination(self, lines: list[str]) -> None:
            """Claim, blocked state, and recent handoff notes."""
            obj = self._obj()
            if obj.get("blocked"):
                reason = str(obj.get("blocked_reason", "") or "").strip()
                lines.append(
                    f"\n[red]blocked[/] {escape_markup(reason) if reason else ''}".rstrip()
                )
            gate = obj.get("gate")
            if gate:
                lines.append(
                    f"\n[dim]gate[/] {escape_markup(str(gate.get('state')))} · "
                    f"{gate.get('prs', 0)} PRs"
                )
            claim = obj.get("claim")
            if claim:
                expires = int(float(claim.get("expires_at") or 0))
                state = "expired" if expires and expires <= int(time.time()) else "active"
                lines.append(
                    f"\n[dim]claim[/] @{escape_markup(str(claim.get('actor', '')))} ({state})"
                )
            comments = [
                comment
                for comment in (self._full.get("comments") or obj.get("comments") or [])
                if not comment.get("resolved")
            ]
            if comments:
                lines.extend(["", f"[dim]comments {len(comments)}[/]"])
                for comment in comments[-3:]:
                    lines.append(
                        f"  [dim]@{escape_markup(str(comment.get('actor', '')))}[/] "
                        f"{escape_markup(str(comment.get('text', '')))}"
                    )
            notes = self._full.get("notes") or obj.get("notes") or []
            if notes:
                lines.extend(["", f"[dim]notes {len(notes)}[/]"])
                for note in notes[-3:]:
                    lines.append(
                        f"  [dim]@{escape_markup(str(note.get('actor', '')))}[/] "
                        f"{escape_markup(str(note.get('text', '')))}"
                    )

        def _read_criteria(self, lines: list[str]) -> None:
            crits = self._full.get("criteria", [])
            if not crits:
                return
            done = sum(1 for crit in crits if crit.get("done"))
            lines.extend(["", f"[dim]acceptance {done}/{len(crits)}[/]"])
            for crit in crits:
                mark = "●" if crit.get("done") else "○"
                lines.append(f"  {mark} {escape_markup(str(crit.get('text', '')))}")

        def _read_children(self, lines: list[str]) -> None:
            if self.dkind == "plan":
                milestones = self._full.get("milestones", [])
                if not milestones:
                    return
                lines.extend(["", f"[dim]milestones {len(milestones)}[/]"])
                for entry in milestones:
                    milestone = entry["milestone"]
                    tasks = entry.get("tasks", [])
                    tasks_done = sum(1 for task in tasks if task.get("status") == "done")
                    lines.append(
                        f"  {status_word(str(milestone.get('status', '')), 'rich')} "
                        f"[dim]M{milestone.get('id')}[/] "
                        f"{escape_markup(str(milestone.get('title', '')))} "
                        f"[dim]{tasks_done}/{len(tasks)}[/]"
                    )
                return
            if self.dkind != "milestone":
                return
            tasks = [entry.get("task", {}) for entry in self._full.get("tasks", [])]
            if not tasks:
                return
            lines.extend(["", f"[dim]tasks {len(tasks)}[/]"])
            for task in tasks:
                lines.append(
                    f"  {status_word(str(task.get('status', '')), 'rich')} "
                    f"[dim]T{task.get('id')}[/] "
                    f"{escape_markup(str(task.get('title', '')))}"
                )

        def _remote_urls(self, links: list[dict[str, Any]]) -> dict[str, str]:
            """Origin URL per linked repo, using stored remotes before git."""
            stored = {
                str(repo.get("repo_path", "") or ""): str(repo.get("repo_remote", "") or "")
                for repo in self._full.get("effective_repos") or self._full.get("repos") or []
            }
            cache: dict[str, str] = {}
            for link in links:
                repo = str(link.get("repo_root", "") or "")
                if not repo or repo in cache:
                    continue
                remote = stored.get(repo, "")
                if not remote:
                    backend, root = detect_backend(repo)
                    if backend is not None and root is not None:
                        remote = origin_url(backend, root)
                cache[repo] = remote
            return cache

        def _read_git(self, lines: list[str]) -> None:
            rows: list[str] = []
            for repo in self._trail.repos if self._trail is not None else ():
                branch = repo.branch or ("detached" if repo.detached else "unknown")
                state = "dirty" if repo.dirty else "clean"
                tracking = (
                    f"{repo.ahead} ahead, {repo.behind} behind" if repo.branch else "no upstream"
                )
                rows.append(
                    f"  {escape_markup(repo.name or repo.path)} · {branch} · {state} · {tracking}"
                )
            if rows:
                lines.extend(["", "[dim]git[/]", *rows])

        def _read_forge(self, lines: list[str]) -> None:
            links = self._full.get("effective_forge_links") or self._full.get("forge_links") or []
            if not links:
                return
            lines.extend(["", "[dim]pull requests[/]"])
            for line in render_forge_links(links).splitlines():
                lines.append(f"  {escape_markup(line)}")

        def _read_source(self, lines: list[str]) -> None:
            trail = self._trail or build_source_trail(self._dstore, self.dkind, self.doid)
            if trail.empty:
                lines.extend(
                    [
                        "",
                        "[dim]source[/]",
                        "  [dim]no linked commits or PRs · link a commit or run task finish[/]",
                    ]
                )
                return
            summary = (
                f"{trail.commit_count} commits · {trail.file_count} files · {trail.pull_count} PRs"
            )
            if trail.stale_count:
                summary += f" · {trail.stale_count} stale"
            lines.extend(["", f"[dim]source · {summary}[/]"])
            for repo in trail.repos[:3]:
                state = "dirty" if repo.dirty else "clean"
                branch = repo.branch or ("detached" if repo.detached else "unknown")
                lines.append(
                    f"  [bold]{escape_markup(repo.name)}[/] · "
                    f"{escape_markup(branch)} · {state} · "
                    f"{len(repo.commits)}c · {len(repo.pulls)}PR"
                )
                for commit in repo.commits[:2]:
                    files = f" · {len(commit.files)} files" if commit.files else ""
                    stale = " · stale" if commit.stale else ""
                    lines.append(
                        f"    [dim]{commit.short}[/] "
                        f"{escape_markup(commit.subject or '(no subject)')}"
                        f"[dim]{files}{stale}[/]"
                    )
                if repo.error:
                    lines.append(f"    [red]{escape_markup(repo.error)}[/]")
            if len(trail.repos) > 3:
                lines.append(f"  [dim]+{len(trail.repos) - 3} more repos[/]")
            lines.append("  [dim]g source trail[/]")

        def _read_links(self, lines: list[str]) -> None:
            links = self._full.get("effective_links") or self._full.get("links") or []
            if links:
                remotes = self._remote_urls(links)
                lines.extend(["", "[dim]commits[/]"])
                for link in links:
                    text = render_commits([link])
                    url = commit_url(
                        remotes.get(str(link.get("repo_root", "") or ""), ""),
                        str(link.get("sha", "")),
                    )
                    suffix = f" [dim]{escape_markup(url)}[/]" if url else ""
                    lines.append(f"  {escape_markup(text)}{suffix}")
            repos = self._full.get("effective_repos") or self._full.get("repos") or []
            if not repos:
                return
            lines.extend(["", "[dim]repos[/]"])
            for repo in repos:
                path = str(repo.get("repo_path", ""))
                remote = str(repo.get("repo_remote", "") or "")
                branch = str(repo.get("branch", "") or "")
                lines.append(
                    f"  {path}"
                    + (f" ({remote})" if remote else "")
                    + (f" · {branch}" if branch else "")
                )

        def _render_read(self) -> None:
            obj = self._obj()
            title = str(obj.get("title", obj.get("name", "")))
            status = str(obj.get("status", ""))
            lines = [f"{status_word(status, 'rich')} [bold]{escape_markup(title)}[/]"]
            self.query_one("#detail-head", Static).update(f"[dim]{self._breadcrumb()}[/]")
            self._read_text(lines, obj)
            self._read_coordination(lines)
            self._read_criteria(lines)
            self._read_children(lines)
            self._read_forge(lines)
            self._read_source(lines)
            self._read_git(lines)
            self._read_links(lines)
            self.query_one("#detail-body", Static).update("\n".join(lines))

        def _form_snapshot(self) -> tuple[str, ...]:
            values = [
                self.query_one("#d-title", Input).value,
                self.query_one("#d-desc", TextArea).text,
            ]
            if self.dkind == "plan":
                values.append(self.query_one("#d-why", Input).value)
            return tuple(values)

        def _is_dirty(self) -> bool:
            return self._snapshot is not None and self._form_snapshot() != self._snapshot

        def _show_mode(self) -> None:
            self.query_one("#detail-read", VerticalScroll).display = not self._editing
            self.query_one("#detail-edit", VerticalScroll).display = self._editing
            hints = (
                "ctrl+s save · esc cancel"
                if self._editing
                else "e edit · s status · x tick · a criterion · g source · n child · d delete · esc back"
            )
            self.query_one("#detail-hints", Label).update(hints)

        def _reload(self) -> None:
            self._editing = False
            self._snapshot = None
            if self._load():
                self._show_mode()
                self._render_read()
                self.query_one("#detail-read", VerticalScroll).focus()

        def action_toggle_edit(self) -> None:
            if self._editing:
                if self._is_dirty():
                    self.notify("save or cancel first")
                    return
                self._editing = False
                self._show_mode()
                self._render_read()
                self.query_one("#detail-read", VerticalScroll).focus()
                return
            self._editing = True
            self._snapshot = self._form_snapshot()
            self._show_mode()
            self.query_one("#d-title", Input).focus()

        def action_open_source(self) -> None:
            """Open the read-only source trail for this row."""
            from .source import SourceScreen

            self.app.push_screen(SourceScreen(self._dstore, self.dkind, self.doid))

        def action_back(self) -> None:
            if self._editing and self._is_dirty():

                def cb(confirmed: bool | None) -> None:
                    if confirmed:
                        self.dismiss(None)

                self.app.push_screen(
                    ConfirmScreen(
                        "Discard your unsaved changes?",
                        confirm_label="Discard",
                        variant="warning",
                    ),
                    cb,
                )
                return
            self.dismiss(None)

        def action_save(self) -> None:
            if not self._editing:
                return
            title = self.query_one("#d-title", Input).value.strip()
            desc = self.query_one("#d-desc", TextArea).text
            if not title:
                self.notify("title must not be empty")
                return
            try:
                if self.dkind == "plan":
                    self._dstore.update_plan(
                        self.doid,
                        name=title,
                        description=desc,
                        goal=self.query_one("#d-why", Input).value or None,
                        actor="tui",
                    )
                elif self.dkind == "milestone":
                    self._dstore.update_milestone(
                        self.doid, title=title, description=desc, actor="tui"
                    )
                else:
                    self._dstore.update_task(self.doid, title=title, description=desc, actor="tui")
            except ValueError as exc:
                self.notify(msg_error(exc))
                return
            from ...messages import RowAction  # noqa: F401

            self.post_message(RowAction("detail-saved", self.dkind, self.doid))
            self._reload()
            self.notify("saved")

        def action_advance_status(self) -> None:
            if self._editing:
                self.notify("save or cancel first")
                return
            nxt = services.cycle_status(self._dstore, self.dkind, self.doid, actor="tui")
            self._reload()
            if nxt is not None:
                self.notify(f"{self.dkind} {self.doid} -> {nxt.value}")

        def action_tick_criterion(self) -> None:
            if self._editing:
                self.notify("save or cancel first")
                return
            items = self._dstore.list_criteria(self.dkind, self.doid)
            open_items = [c for c in items if not c.done]
            if not open_items:
                self.notify("no open criteria")
                return
            target = open_items[0]
            self._dstore.set_criteria(target.id, True, actor="tui")
            self._reload()
            self.notify(f"criterion {target.id} checked")

        def action_add_criterion(self) -> None:
            if self._editing:
                self.notify("save or cancel first")
                return

            def cb(text: str | None) -> None:
                if not text:
                    return
                self._dstore.add_criteria(self.dkind, self.doid, text, actor="tui")
                self._reload()

            self.app.push_screen(
                FilterPromptScreen(
                    title=f"New criterion on {self.dkind} {self.doid}",
                    placeholder="what must be true?",
                    submit_label="Add",
                ),
                cb,
            )

        def action_add_child(self) -> None:
            if self._editing:
                self.notify("save or cancel first")
                return
            if self.dkind == "plan":
                plan_id = self.doid

                def add_milestone(data: dict | None) -> None:
                    if not data:
                        return
                    services.create_milestone(
                        self._dstore,
                        plan_id,
                        data["title"],
                        data["desc"],
                        actor="tui",
                    )
                    self._reload()

                self.app.push_screen(
                    NewMilestoneScreen(
                        plan_id,
                        defaults=load_template("milestone", self._dstore.path).defaults,
                        context=f"P{plan_id}",
                    ),
                    add_milestone,
                )
                return
            if self.dkind == "milestone":
                milestone_id = self.doid

                def add_task(data: dict | None) -> None:
                    if not data:
                        return
                    services.create_task(
                        self._dstore,
                        milestone_id,
                        data["title"],
                        data["desc"],
                        actor="tui",
                    )
                    self._reload()

                self.app.push_screen(
                    NewTaskScreen(
                        milestone_id,
                        defaults=load_template("task", self._dstore.path).defaults,
                        context=str(self._breadcrumb()),
                    ),
                    add_task,
                )
                return
            self.notify("tasks have no children; add a criterion instead (a)")

        def action_delete_row(self) -> None:
            if self._editing:
                self.notify("save or cancel first")
                return
            title = str(self._obj().get("title", self._obj().get("name", "")))
            lines = [f'Delete {self.dkind} {self.doid} "{title}"?']
            criteria = len(self._dstore.list_criteria(self.dkind, self.doid))
            if self.dkind == "plan":
                milestones = self._dstore.list_milestones(self.doid)
                tasks = sum(len(self._dstore.list_tasks(m.id)) for m in milestones)
                lines.append(
                    f"Also deletes {len(milestones)} milestones, {tasks} tasks, "
                    f"{criteria} criteria."
                )
            elif self.dkind == "milestone":
                tasks = len(self._dstore.list_tasks(self.doid))
                lines.append(f"Also deletes {tasks} tasks and {criteria} criteria.")
            elif criteria:
                lines.append(f"Also deletes {criteria} criteria.")

            def cb(confirmed: bool | None) -> None:
                if not confirmed:
                    return
                self._dstore.delete(self.dkind, self.doid, actor="tui")
                self.dismiss(True)

            self.app.push_screen(ConfirmScreen("\n".join(lines)), cb)
