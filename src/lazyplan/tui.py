"""Single-panel Textual TUI: tree | gantt | feed, nano-style bottom bar.

Keys: 1/2/3 views, j/k navigate, z/Z fold one/all, n contextual new, P/S/T new project/story/task,
  e edit, space cycle status, enter detail, +/- gantt zoom, f status filter,
  o project filter, r refresh, ? help, q quit. Mouse click folds/unfolds too.
Command bar accepts the same verbs as `lp`, e.g. `add-task --story 1 --title x`.
Agent writes via `lp --actor NAME ...` land in the same SQLite file; the TUI
polls fingerprint() every second and toasts + activity-line.
"""

from __future__ import annotations

from typing import Any, cast

try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Vertical
    from textual.widgets import Footer, Header, Input, Label, OptionList, Static, Tree
    from textual.widgets.tree import TreeNode

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from .design import (
    APP_CSS,
    EMPTY_FEED,
    EMPTY_FILTERED,
    EMPTY_NO_PROJECTS,
    msg_error,
    project_label,
    story_label,
    task_label,
)
from .gantt import bar, span
from .models import Project, Status, Task, UserStory
from .repo import repo_label
from .screens import (
    ConfirmScreen,
    DetailScreen,
    EditScreen,
    HelpScreen,
    NewProjectScreen,
    NewStoryScreen,
    NewTaskScreen,
    PaletteScreen,
    SearchScreen,
)
from .store import Store

STATUS_CYCLE: list[Status | None] = [None, Status.TODO, Status.DOING, Status.DONE]

if _TEXTUAL_OK:

    class FoldTree(Tree):
        """Project/story tree with app-level key semantics.

        The native Tree space/shift+space bindings stay (so they keep working
        and mouse toggles are untouched), but their actions delegate to the
        app: `space` cycles status, shift+space folds all. Folding one node
        lives on `z`; collapse state is tracked in app._collapsed.
        """

        def action_toggle_node(self) -> None:
            """Space: cycle status instead of toggling the node."""
            cast("LazyplanApp", self.app).action_toggle_status()

        def action_toggle_expand_all(self) -> None:
            """Shift+space: fold-all with app semantics."""
            cast("LazyplanApp", self.app).action_fold_all()

    class LazyplanApp(App):
        """Single-panel TUI: tree | gantt | feed | proposals."""

        TITLE = "lazyplan"
        CSS = APP_CSS
        BINDINGS = [
            Binding("1", "view_tree", "Tree"),
            Binding("2", "view_gantt", "Gantt"),
            Binding("3", "view_feed", "Feed"),
            Binding("4", "view_props", "Propose"),
            Binding("ctrl+p", "palette", "Palette"),
            Binding("s", "search", "Search"),
            Binding("j", "cursor_down", "Down", show=False),
            Binding("k", "cursor_up", "Up", show=False),
            Binding("n", "new_context", "New"),
            Binding("P", "new_project", "NewProj", show=False),
            Binding("S", "new_story", "NewStory", show=False),
            Binding("T", "new_task", "NewTask", show=False),
            Binding("e", "edit", "Edit"),
            Binding("a", "props_approve", "Approve"),
            Binding("x", "props_reject", "Reject"),
            Binding("c", "criteria", "Check"),
            Binding("d", "delete", "Delete"),
            Binding("space", "toggle_status", "Done"),
            Binding("z", "fold", "Fold"),
            Binding("Z", "fold_all", "FoldAll", show=False),
            Binding("left", "fold_left", "Fold", show=False),
            Binding("right", "fold_right", "Unfold", show=False),
            Binding("plus", "zoom_in", "Zoom+"),
            Binding("minus", "zoom_out", "Zoom-"),
            Binding("f", "filter_status", "Filter"),
            Binding("o", "filter_project", "Proj"),
            Binding("O", "filter_owner", "Owner"),
            Binding("r", "refresh", "Refresh"),
            Binding("question_mark", "help", "Help"),
            Binding("slash", "focus_cmd", "Cmd"),
            Binding("q", "quit", "Quit"),
        ]

        def __init__(self, store: Store) -> None:
            super().__init__()
            self.store = store
            self.mode = "tree"
            self.selected: tuple[str, int] | None = None
            self.status_filter: Status | None = None
            self.project_filter: int | None = None
            self.owner_filter: str | None = None
            self.gantt_width = 40
            self._row_nodes: dict[tuple[str, int], TreeNode] = {}
            self._collapsed: set[tuple[str, int]] = set()
            self._fp: Any = store.fingerprint()

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            with Vertical(id="panel"):
                yield FoldTree("projects", id="tree")
                yield Static("", id="gantt", markup=False)
                yield Static("", id="feed", markup=False)
                yield OptionList(id="props")
            yield Label("", id="activity")
            yield Label("", id="statusbar")
            yield Input(
                placeholder=": help · agents inject via `lp --actor NAME add-task ...`", id="cmdbar"
            )
            yield Footer()

        def on_mount(self) -> None:
            self.query_one("#gantt", Static).display = False
            self.query_one("#feed", Static).display = False
            self.query_one("#props", OptionList).display = False
            self.refresh_all("ready — ? help")
            self.set_interval(1.0, self._poll)
            self.query_one("#tree", Tree).focus()

        def action_focus_cmd(self) -> None:
            self.query_one("#cmdbar", Input).focus()

        # -- selection --------------------------------------------------
        def _track(self, node: TreeNode) -> None:
            data = getattr(node, "data", None)
            if isinstance(data, dict) and "kind" in data and "id" in data:
                self.selected = (data["kind"], int(data["id"]))

        def on_tree_node_highlighted(self, e: Tree.NodeHighlighted) -> None:
            self._track(e.node)

        @staticmethod
        def _node_key(node: TreeNode) -> tuple[str, int] | None:
            data = getattr(node, "data", None)
            if isinstance(data, dict) and "kind" in data and "id" in data:
                return (str(data["kind"]), int(data["id"]))
            return None

        def on_tree_node_collapsed(self, e: Tree.NodeCollapsed) -> None:
            """Remember mouse folds across refreshes/polls."""
            key = self._node_key(e.node)
            if key is not None and key[0] in ("project", "story"):
                self._collapsed.add(key)

        def on_tree_node_expanded(self, e: Tree.NodeExpanded) -> None:
            key = self._node_key(e.node)
            if key is not None:
                self._collapsed.discard(key)

        def action_cursor_down(self) -> None:
            self.query_one("#tree", Tree).action_cursor_down()

        def action_cursor_up(self) -> None:
            self.query_one("#tree", Tree).action_cursor_up()

        def action_fold(self) -> None:
            """Toggle the selected project/story open/closed (z)."""
            if self.selected is None:
                self.notify("select a row first (z folds it)")
                return
            node = self._row_nodes.get(self.selected)
            if node is None or not node.allow_expand or not node.children:
                self.notify("nothing to fold here")
                return
            key = self.selected
            if key in self._collapsed:
                node.expand()
                self._collapsed.discard(key)
                self.refresh_all(f"{key[0]} #{key[1]} unfolded")
            else:
                node.collapse()
                self._collapsed.add(key)
                self.refresh_all(f"{key[0]} #{key[1]} folded")

        def action_fold_all(self) -> None:
            """Collapse every project/story, or re-open all when fully folded (Z)."""
            keys = [k for k, n in self._row_nodes.items() if n.allow_expand and n.children]
            if not keys:
                self.notify("nothing to fold")
                return
            if all(k in self._collapsed for k in keys):
                for k in keys:
                    self._row_nodes[k].expand()
                self._collapsed.clear()
                self.refresh_all("unfolded all")
            else:
                for k in keys:
                    self._row_nodes[k].collapse()
                    self._collapsed.add(k)
                self.refresh_all(f"folded {len(keys)} rows")

        def _children_of(self, kind: str, oid: int) -> list[tuple[str, int]]:
            """Visible child row keys, in tree order."""
            if kind == "project":
                return [
                    ("story", s.id)
                    for s in self.store.list_stories(oid)
                    if ("story", s.id) in self._row_nodes
                ]
            if kind == "story":
                return [
                    ("task", t.id)
                    for t in self.store.list_tasks(oid)
                    if ("task", t.id) in self._row_nodes
                ]
            return []

        def _parent_of(self, kind: str, oid: int) -> tuple[str, int] | None:
            if kind == "story":
                s = self.store.get_story(oid)
                return ("project", s.project_id) if s else None
            if kind == "task":
                t = self.store.get_task(oid)
                return ("story", t.story_id) if t else None
            return None

        def action_fold_left(self) -> None:
            """Left: collapse the header, else jump to its parent."""
            if self.mode != "tree" or self.selected is None:
                return
            kind, oid = self.selected
            node = self._row_nodes.get(self.selected)
            if (
                node is not None
                and node.allow_expand
                and node.children
                and (kind, oid) not in self._collapsed
            ):
                node.collapse()
                self._collapsed.add((kind, oid))
                self.refresh_all(f"{kind} #{oid} folded")
                return
            parent = self._parent_of(kind, oid)
            if parent is not None and parent in self._row_nodes:
                self.query_one("#tree", Tree).move_cursor(self._row_nodes[parent])

        def action_fold_right(self) -> None:
            """Right: expand the header, else jump to its first child."""
            if self.mode != "tree" or self.selected is None:
                return
            kind, oid = self.selected
            node = self._row_nodes.get(self.selected)
            if node is not None and (kind, oid) in self._collapsed:
                node.expand()
                self._collapsed.discard((kind, oid))
                self.refresh_all(f"{kind} #{oid} unfolded")
                return
            for child in self._children_of(kind, oid):
                self.query_one("#tree", Tree).move_cursor(self._row_nodes[child])
                return

        # -- polling (M3: fingerprint, not just mtime) -------------------
        def _poll(self) -> None:
            fp = self.store.fingerprint()
            if fp != self._fp:
                self._fp = fp
                events = self.store.feed(1)
                note = "db changed — refreshed"
                if events:
                    e = events[0]
                    note = f"[{e['actor']}] {e['kind']}/{e['action']}: {e['detail']}"
                    self.notify(note, timeout=4)
                self.refresh_all(note)

        # -- rendering ---------------------------------------------------
        def _filtered_tree(
            self,
        ) -> list[tuple[Project, list[tuple[UserStory, list[Task]]]]]:
            return self.store.tree(
                status=self.status_filter, project_id=self.project_filter, owner=self.owner_filter
            )

        def refresh_all(self, note: str = "") -> None:
            tree = self.query_one("#tree", Tree)
            tree.clear()
            self._row_nodes = {}
            root = tree.root
            for p, stories in self._filtered_tree():
                pn = root.add(
                    project_label(p),
                    data={"kind": "project", "id": p.id},
                    allow_expand=bool(stories),
                )
                self._row_nodes[("project", p.id)] = pn
                for s, tasks in stories:
                    sn = pn.add(
                        story_label(s, self.store),
                        data={"kind": "story", "id": s.id},
                        allow_expand=bool(tasks),
                    )
                    self._row_nodes[("story", s.id)] = sn
                    for t in tasks:
                        leaf = sn.add_leaf(
                            task_label(t, self.store), data={"kind": "task", "id": t.id}
                        )
                        self._row_nodes[("task", t.id)] = leaf
            root.expand()
            self._collapsed &= set(self._row_nodes)  # drop rows deleted since last build
            for key, node in self._row_nodes.items():
                if key in self._collapsed:
                    node.collapse()
                elif node.allow_expand:
                    node.expand()
            self._render_gantt()
            self._render_feed()
            self._render_props()
            c = self.store.counts()
            events = self.store.feed(1)
            act = ""
            if events:
                e = events[0]
                act = f"last: [{e['actor']}] {e['kind']}/{e['action']}: {e['detail']}"
            self.query_one("#activity", Label).update(" " + act)
            sf = self.status_filter.value if self.status_filter else "all"
            pf = f"P#{self.project_filter}" if self.project_filter else "all"
            ow = f"@{self.owner_filter}" if self.owner_filter else "all"
            self.query_one("#statusbar", Label).update(
                f" [{repo_label(self.store.path)}]"
                f" P:{c['projects']} S:{c['stories']} T:{c['tasks_done']}/{c['tasks']}"
                f" · f:{sf} o:{pf} O:{ow} w:{self.gantt_width}" + (f" — {note}" if note else "")
            )

        def _render_gantt(self) -> None:
            tree = self._filtered_tree()
            dates: list[str] = []
            ms_by_project: dict[int, list] = {}
            for p, stories in tree:
                ms_by_project[p.id] = self.store.list_milestones(p.id)
                for s, tasks in stories:
                    dates += [s.start_date, s.end_date]
                    for t in tasks:
                        dates += [t.start_date, t.end_date]
            for ms in ms_by_project.values():
                dates += [m.date for m in ms if m.date]
            dates = [d for d in dates if d]
            lo, hi = span(dates, self.gantt_width)
            lines = [f"{lo} .. {hi} (w={self.gantt_width}, +/- zoom)"]
            for p, stories in tree:
                lines.append(f"P#{p.id} {p.name}")
                crit = set(self.store.critical_path(p.id))
                for m in ms_by_project.get(p.id, []):
                    lines.append(f"  ◆ {m.date or '????-??-??'} M#{m.id} {m.title}")
                for s, tasks in stories:
                    mark = ("*" if s.id in crit else " ") + (
                        "!" if self.store.is_blocked("story", s.id) else " "
                    )
                    lines.append(
                        f"{mark} S#{s.id:>3} {bar(s.start_date, s.end_date, lo, hi, self.gantt_width)}"
                        f" {s.title} [{s.status.value}]"
                    )
                    for t in tasks:
                        tmark = " " + ("!" if self.store.is_blocked("task", t.id) else " ")
                        b = (
                            bar(t.start_date, t.end_date, lo, hi, self.gantt_width)
                            if (t.start_date and t.end_date)
                            else "(no dates)"
                        )
                        lines.append(f"{tmark} T#{t.id:>3} {b} {t.title} [{t.status.value}]")
            if not tree:
                lines.append(
                    EMPTY_NO_PROJECTS if not self.store.list_projects() else EMPTY_FILTERED
                )
            self.query_one("#gantt", Static).update("\n".join(lines))

        def _render_feed(self) -> None:
            lines: list[str] = []
            for q in self.store.list_questions():
                lines.append(f"❓ Q#{q['id']} [{q['actor']}] {q['question']}")
                lines.append(f'   answer via: answer --id {q["id"]} --text "..."')
            events = self.store.feed(15)
            if not events and not lines:
                self.query_one("#feed", Static).update(EMPTY_FEED)
                return
            lines.extend(
                f"#{e['id']} [{e['actor']}] {e['kind']}/{e['action']}: {e['detail']}"
                for e in reversed(events)
            )
            self.query_one("#feed", Static).update("\n".join(lines))

        def _render_props(self) -> None:
            from textual.widgets._option_list import Option as _Option

            lst = self.query_one("#props", OptionList)
            lst.clear_options()
            pend = self.store.list_proposals("pending")
            if not pend:
                lst.add_option(
                    _Option("(no pending proposals — agents submit via lp propose)", id="none")
                )
                return
            import json as _json

            for pr in pend:
                try:
                    fields = _json.loads(pr["payload"] or "{}")
                    title = fields.get("title", "?")
                except (ValueError, TypeError, AttributeError):
                    # Corrupt payload row must not crash the view; id still shown.
                    title = "?"
                lst.add_option(
                    _Option(f"#{pr['id']} [{pr['actor']}] {pr['kind']} → {title}", id=str(pr["id"]))
                )

        # -- view actions -------------------------------------------------
        def _show(self, mode: str) -> None:
            self.mode = mode
            self.query_one("#tree", Tree).display = mode == "tree"
            self.query_one("#gantt", Static).display = mode == "gantt"
            self.query_one("#feed", Static).display = mode == "feed"
            self.query_one("#props", OptionList).display = mode == "props"

        def action_view_tree(self) -> None:
            self._show("tree")

        def action_view_gantt(self) -> None:
            self._show("gantt")
            self._render_gantt()

        def action_view_feed(self) -> None:
            self._show("feed")
            self._render_feed()

        def action_view_props(self) -> None:
            self._show("props")
            self._render_props()

        def _pending_selection(self) -> dict | None:
            lst = self.query_one("#props", OptionList)
            pend = self.store.list_proposals("pending")
            if not pend:
                return None
            idx = lst.highlighted
            if idx is None or idx >= len(pend):
                idx = 0  # nothing highlighted yet: act on the first pending item
            return pend[idx]

        def action_props_approve(self) -> None:
            pr = self._pending_selection()
            if pr is None:
                self.notify("no pending proposal highlighted (4 = proposals view)")
                return
            try:
                res = self.store.decide_proposal(pr["id"], True, actor="tui")
            except ValueError as exc:
                self.notify(msg_error(exc))
                return
            self._fp = self.store.fingerprint()
            self.refresh_all(f"approved proposal #{pr['id']} -> {res['result_id'] if res else '?'}")

        def action_props_reject(self) -> None:
            pr = self._pending_selection()
            if pr is None:
                self.notify("no pending proposal highlighted (4 = proposals view)")
                return
            self.store.decide_proposal(pr["id"], False, actor="tui")
            self._fp = self.store.fingerprint()
            self.refresh_all(f"rejected proposal #{pr['id']}")

        def action_refresh(self) -> None:
            self._fp = self.store.fingerprint()
            self.refresh_all("manual refresh")

        def action_zoom_in(self) -> None:
            self.gantt_width = min(self.gantt_width + 10, 100)
            self._render_gantt()
            self.refresh_all(f"zoom w={self.gantt_width}")

        def action_zoom_out(self) -> None:
            self.gantt_width = max(self.gantt_width - 10, 20)
            self._render_gantt()
            self.refresh_all(f"zoom w={self.gantt_width}")

        def action_filter_status(self) -> None:
            i = STATUS_CYCLE.index(self.status_filter)
            self.status_filter = STATUS_CYCLE[(i + 1) % len(STATUS_CYCLE)]
            self.refresh_all(
                f"status filter: {self.status_filter.value if self.status_filter else 'all'}"
            )

        def action_filter_project(self) -> None:
            ids = [p.id for p in self.store.list_projects()]
            order: list[int | None] = [None, *ids]
            try:
                i = order.index(self.project_filter)
            except ValueError:
                i = 0
            self.project_filter = order[(i + 1) % len(order)]
            self.refresh_all(f"project filter: {self.project_filter or 'all'}")

        def action_filter_owner(self) -> None:
            owners = self.store.distinct_owners()
            order: list[str | None] = [None, *owners]
            try:
                i = order.index(self.owner_filter)
            except ValueError:
                i = 0
            self.owner_filter = order[(i + 1) % len(order)]
            self.refresh_all(f"owner filter: {self.owner_filter or 'all'}")

        def action_help(self) -> None:
            self.push_screen(HelpScreen())

        # -- M2 editing ----------------------------------------------------
        def _story_for_task_ctx(self) -> int | None:
            if self.selected is None:
                return None
            kind, oid = self.selected
            if kind == "story":
                return oid
            if kind == "task":
                t = self.store.get_task(oid)
                return t.story_id if t else None
            return None

        def _project_ctx(self) -> int | None:
            if self.project_filter is not None:
                return self.project_filter
            if self.selected is None:
                return None
            kind, oid = self.selected
            if kind == "project":
                return oid
            if kind == "story":
                s = self.store.get_story(oid)
                return s.project_id if s else None
            if kind == "task":
                t = self.store.get_task(oid)
                if t is None:
                    return None
                s = self.store.get_story(t.story_id)
                return s.project_id if s else None
            return None

        def action_palette(self) -> None:
            def cb(res: tuple[str, str] | None) -> None:
                """Modal dismiss callback."""
                if res:
                    self.action_goto(*res)

            self.push_screen(PaletteScreen(self.store), cb)

        def action_search(self) -> None:
            def cb(res: tuple[str, str] | None) -> None:
                if res:
                    self.action_goto(*res)

            self.push_screen(SearchScreen(self.store), cb)

        def action_goto(self, kind: str, ref: str) -> None:
            if kind == "cmd":
                {
                    "tree": self.action_view_tree,
                    "gantt": self.action_view_gantt,
                    "feed": self.action_view_feed,
                    "props": self.action_view_props,
                }.get(ref, self.action_view_tree)()
                if ref == "help":
                    self.push_screen(HelpScreen())
                return
            try:
                oid = int(ref)
            except ValueError:
                self.notify(f"bad pick: {kind}:{ref}")
                return
            self._show("tree")
            node = self._row_nodes.get((kind, oid))
            if node is None:
                self.refresh_all("")
                node = self._row_nodes.get((kind, oid))
            if node is None:
                self.notify("row gone — refreshed")
                return
            tree = self.query_one("#tree", Tree)
            tree.select_node(node)
            tree.scroll_to_node(node)
            self.selected = (kind, oid)

        def action_new_context(self) -> None:
            sid = self._story_for_task_ctx()
            if sid is not None:
                self.action_new_task()
                return
            pid = self._project_ctx()
            if pid is not None:
                self.action_new_story()
                return
            self.action_new_project()

        def action_new_project(self) -> None:
            def cb(data: dict | None) -> None:
                if not data:
                    return
                try:
                    self.store.add_project(
                        data["name"], data["desc"], data["start"], data["end"], actor="tui"
                    )
                except ValueError as exc:
                    self.notify(f"error: {exc}")
                self._fp = self.store.fingerprint()
                self.refresh_all("project created")

            self.push_screen(NewProjectScreen(), cb)

        def action_new_story(self) -> None:
            pid = self._project_ctx()
            if pid is None:
                projects = self.store.list_projects()
                if not projects:
                    self.notify("no projects — press P to create one first")
                    return
                pid = projects[0].id

            def cb(data: dict | None) -> None:
                if not data:
                    return
                try:
                    self.store.add_story(
                        pid, data["title"], data["desc"], data["start"], data["end"], actor="tui"
                    )
                except (ValueError, KeyError) as exc:
                    self.notify(f"error: {exc}")
                self._fp = self.store.fingerprint()
                self.refresh_all("story created")

            self.push_screen(NewStoryScreen(pid), cb)

        def action_new_task(self) -> None:
            sid = self._story_for_task_ctx()
            if sid is None:
                self.notify("select a story first (or press S to create one)")
                return

            def cb(data: dict | None) -> None:
                if not data:
                    return
                try:
                    self.store.add_task(
                        sid, data["title"], data["est"], data["start"], data["end"], actor="tui"
                    )
                except (ValueError, KeyError) as exc:
                    self.notify(f"error: {exc}")
                self._fp = self.store.fingerprint()
                self.refresh_all("task created")

            self.push_screen(NewTaskScreen(sid), cb)

        def action_edit(self) -> None:
            if self.selected is None:
                self.notify("select a row first (j/k + click)")
                return
            kind, oid = self.selected
            obj: Project | UserStory | Task | None = None
            if kind == "project":
                obj = self.store.get_project(oid)
                title, extra, owner = (obj.name, obj.description, "") if obj else ("", "", "")
            elif kind == "story":
                obj = self.store.get_story(oid)
                title, extra = (obj.title, obj.description) if obj else ("", "")
                owner = obj.owner if obj else ""
            else:
                obj = self.store.get_task(oid)
                title, extra = (obj.title, obj.estimate) if obj else ("", "")
                owner = obj.owner if obj else ""
            if obj is None:
                self.notify("selected row no longer exists — refreshing")
                self.refresh_all("")
                return

            def cb(data: dict | None) -> None:
                if not data:
                    return
                try:
                    if kind == "project":
                        self.store.update_project(
                            oid, name=data["title"], description=data["extra"], actor="tui"
                        )
                    elif kind == "story":
                        self.store.update_story(
                            oid,
                            title=data["title"],
                            description=data["extra"],
                            owner=data.get("owner", owner),
                            actor="tui",
                        )
                    else:
                        self.store.update_task(
                            oid,
                            title=data["title"],
                            estimate=data["extra"],
                            owner=data.get("owner", owner),
                            actor="tui",
                        )
                except ValueError as exc:
                    self.notify(f"error: {exc}")
                self._fp = self.store.fingerprint()
                self.refresh_all("saved")

            self.push_screen(EditScreen(kind, oid, title, extra, owner), cb)

        def action_toggle_status(self) -> None:
            if self.selected is None:
                self.notify("select a row first (space cycles its status)")
                return
            kind, oid = self.selected
            if kind in ("story", "task"):
                left = self.store.open_criteria(kind, oid)
                if left and self.store._current_status(kind, oid) != Status.DONE:
                    # advisory only: warn, then proceed (flow first)
                    self.notify(f"warning: {len(left)} open criteria — closing anyway", timeout=5)
            nxt = self.store.cycle_status(kind, oid, actor="tui")
            if nxt is None:
                self.notify("selected row no longer exists")
            self._fp = self.store.fingerprint()
            self.refresh_all(f"{kind} #{oid} -> {nxt.value if nxt else '?'}")

        def action_criteria(self) -> None:
            """Tick first open criterion; if none open, reopen the last done one."""
            if self.selected is None:
                self.notify("select a story/task first (c ticks criteria)")
                return
            kind, oid = self.selected
            if kind not in ("story", "task"):
                self.notify("criteria live on stories and tasks")
                return
            items = self.store.list_criteria(kind, oid)
            if not items:
                self.notify(
                    f'no criteria — add via: add-criteria --kind {kind} --id {oid} --text "..."'
                )
                return
            open_items = [c for c in items if not c.done]
            if open_items:
                target, reopen = open_items[0], False
            else:
                target, reopen = items[-1], True  # nothing open: re-affirm by reopening last
            self.store.set_criteria(target.id, not reopen, actor="tui")
            self._fp = self.store.fingerprint()
            verb = "reopened" if reopen else "checked"
            self.refresh_all(f"criteria #{target.id} {verb}")

        def action_delete(self) -> None:
            if self.selected is None:
                self.notify("select a row first (d deletes with confirm)")
                return
            kind, oid = self.selected

            def cb(confirmed: bool | None) -> None:
                if not confirmed:
                    return
                if not self.store.delete(kind, oid, actor="tui"):
                    self.notify("already gone — refreshing")
                self.selected = None
                self._fp = self.store.fingerprint()
                self.refresh_all(f"deleted {kind} #{oid}")

            self.push_screen(ConfirmScreen(f"Delete {kind} #{oid}?\n(children go too.)"), cb)

        def on_tree_node_selected(self, e: Tree.NodeSelected) -> None:  # enter key: editable detail
            self._track(e.node)
            data = getattr(e.node, "data", None)
            if not isinstance(data, dict):
                return
            kind, oid = data.get("kind"), data.get("id")
            if kind not in ("project", "story", "task") or not isinstance(oid, int):
                self.notify("select a row first, then enter")
                return

            def cb(saved: bool | None) -> None:
                if saved:
                    self._fp = self.store.fingerprint()
                    self.refresh_all("saved detail")

            self.push_screen(DetailScreen(self.store, kind, oid), cb)

        # -- command bar ----------------------------------------------------
        def on_input_submitted(self, event: Input.Submitted) -> None:
            text = event.value.strip()
            event.input.value = ""
            if not text:
                return
            if text in ("help", ":help", "?", "h"):
                self.push_screen(HelpScreen())
                return
            if text in ("q", ":q", "quit"):
                self.exit()
                return
            if text in ("gantt", ":gantt", "2"):
                self.action_view_gantt()
                return
            if text in ("tree", ":tree", "1"):
                self.action_view_tree()
                return
            if text in ("feed", ":feed", "3"):
                self.action_view_feed()
                return
            if text in ("props", "proposals", ":props", ":proposals", "4"):
                self.action_view_props()
                return
            import shlex

            from .cli import build_parser

            try:
                args = build_parser().parse_args(["--db", str(self.store.path), *shlex.split(text)])
            except SystemExit:
                self.notify(f"unknown command: {text} (try help)")
                return
            if args.cmd in ("ui", "feed", "watch", "completion", "help", "export", "import"):
                if args.cmd in ("feed", "watch"):
                    self.action_view_feed()
                elif args.cmd == "help":
                    self.push_screen(HelpScreen())
                else:
                    self.notify(f"{args.cmd}: use the shell, already in UI")
                return
            from . import cli as _cli

            _cli.main(["--db", str(self.store.path), "--actor", "tui", *shlex.split(text)])
            self._fp = self.store.fingerprint()
            self.refresh_all(f"ran: {text}")

    def create_app(db_path: str | None = None) -> LazyplanApp:
        """Build the app bound to a store."""
        return LazyplanApp(Store(db_path))


def run(db_path: str | None = None) -> int:
    """Run the TUI; exit 3 when Textual is missing."""
    if not _TEXTUAL_OK:
        print("Textual not installed. Run: pip install -e . then: lp ui")
        print("Fallback (no TUI): lp list   |   lp gantt")
        return 3
    create_app(db_path).run()
    return 0
