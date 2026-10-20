"""Single-panel Textual TUI: plan tree, nano-style bottom bar.

Keys: j/k navigate, z/Z fold one/all, n contextual new, P/S/T new plan/milestone/task,
  e edit, space cycle status, c tick criteria, enter detail, f status filter,
  o plan filter, r refresh, ? help, q quit. Mouse click folds/unfolds too.
Keyboard-only: agents use the `lpui` CLI against the same SQLite file; the TUI
polls fingerprint() every second and toasts + activity-line.
"""

from __future__ import annotations

import time
from typing import Any, cast

try:
    from textual import events
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Vertical
    from textual.widgets import Footer, Header, Label, Tree
    from textual.widgets.tree import TreeNode

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from . import services
from .design import (
    APP_CSS,
    milestone_row,
    plan_row,
    task_row,
)
from .models import Milestone, Plan, Status, Task
from .repo import repo_label
from .screens import (
    ConfirmScreen,
    DetailScreen,
    EditScreen,
    HelpScreen,
    NewMilestoneScreen,
    NewPlanScreen,
    NewTaskScreen,
)
from .store import Store
from .templates import load_template

STATUS_CYCLE: list[Status | None] = [None, Status.TODO, Status.DOING, Status.DONE]
DOUBLE_CLICK_WINDOW = 0.5  # seconds between two clicks on one row

if _TEXTUAL_OK:

    class FoldTree(Tree):
        """Plan/milestone tree with app-level key semantics.

        The native Tree space/shift+space bindings stay (so they keep working
        and mouse toggles are untouched), but their actions delegate to the
        app: `space` cycles status, shift+space folds all. Folding one node
        lives on `z`; collapse state is tracked in app._collapsed.
        Enter opens the detail dialog instead of merely selecting.
        """

        BINDINGS = [Binding("enter", "open_detail", "Detail")]

        def action_toggle_node(self) -> None:
            """Space: cycle status instead of toggling the node."""
            cast("LazyplanApp", self.app).action_toggle_status()

        def action_toggle_expand_all(self) -> None:
            """Shift+space: fold-all with app semantics."""
            cast("LazyplanApp", self.app).action_fold_all()

        def action_open_detail(self) -> None:
            """Enter: open the detail dialog for the selected row."""
            cast("LazyplanApp", self.app).action_open_detail()

        async def _on_click(self, event: events.Click) -> None:
            """Single click selects; two quick clicks on one row open detail."""
            await super()._on_click(event)
            app = cast("LazyplanApp", self.app)
            meta = event.style.meta
            if "line" not in meta or meta.get("toggle", False):
                return
            try:
                node = self.get_node_at_line(meta["line"])
            except IndexError:
                return
            if node is None:
                return
            key = LazyplanApp._node_key(node)
            if key is not None and app.note_click(key):
                app._open_detail(*key)

    class LazyplanApp(App):
        """Single-panel TUI: the plan tree."""

        TITLE = "lazyplan"
        CSS = APP_CSS
        BINDINGS = [
            Binding("j", "cursor_down", "Down", show=False),
            Binding("k", "cursor_up", "Up", show=False),
            Binding("n", "new_context", "New"),
            Binding("P", "new_plan", "NewPlan", show=False),
            Binding("M", "new_milestone", "NewMilestone", show=False),
            Binding("T", "new_task", "NewTask", show=False),
            Binding("e", "edit", "Edit"),
            Binding("c", "criteria", "Check"),
            Binding("d", "delete", "Delete"),
            Binding("space", "toggle_status", "Done"),
            Binding("enter", "open_detail", "Detail"),
            Binding("z", "fold", "Fold"),
            Binding("Z", "fold_all", "FoldAll", show=False),
            Binding("left", "fold_left", "Fold", show=False),
            Binding("right", "fold_right", "Unfold", show=False),
            Binding("f", "filter_status", "Filter"),
            Binding("o", "filter_plan", "Plan"),
            Binding("A", "toggle_show_all", "All"),
            Binding("r", "refresh", "Refresh"),
            Binding("question_mark", "help", "Help"),
            Binding("q", "quit", "Quit"),
        ]

        def __init__(self, store: Store) -> None:
            super().__init__()
            self.store = store
            self.selected: tuple[str, int] | None = None
            self.status_filter: Status | None = None
            self.plan_filter: int | None = None
            self.show_all: bool = False
            self._row_nodes: dict[tuple[str, int], TreeNode] = {}
            self._collapsed: set[tuple[str, int]] = set()
            self._expanded: set[tuple[str, int]] = set()
            self._last_click_key: tuple[str, int] | None = None
            self._last_click_at: float = 0.0
            self._fp: Any = store.fingerprint()

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            with Vertical(id="panel"):
                yield FoldTree("plans", id="tree")
            yield Label("", id="activity")
            yield Label("", id="statusbar")
            yield Footer()

        def on_mount(self) -> None:
            self.refresh_all("ready — ? help")
            self.set_interval(1.0, self._poll)
            self.query_one("#tree", Tree).focus()

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
            if key is not None and key[0] in ("plan", "milestone"):
                self._collapsed.add(key)
                self._expanded.discard(key)

        def on_tree_node_expanded(self, e: Tree.NodeExpanded) -> None:
            key = self._node_key(e.node)
            if key is not None:
                self._collapsed.discard(key)
                if key[0] == "plan":
                    self._expanded.add(key)

        def action_cursor_down(self) -> None:
            self.query_one("#tree", Tree).action_cursor_down()

        def action_cursor_up(self) -> None:
            self.query_one("#tree", Tree).action_cursor_up()

        def action_fold(self) -> None:
            """Toggle the selected plan/milestone open/closed (z)."""
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
                if key[0] == "plan":
                    self._expanded.add(key)
                self.refresh_all(f"{key[0]} #{key[1]} unfolded")
            else:
                node.collapse()
                self._collapsed.add(key)
                self._expanded.discard(key)
                self.refresh_all(f"{key[0]} #{key[1]} folded")

        def action_fold_all(self) -> None:
            """Collapse every plan/milestone, or re-open all when fully folded (Z)."""
            keys = [k for k, n in self._row_nodes.items() if n.allow_expand and n.children]
            if not keys:
                self.notify("nothing to fold")
                return
            if all(k in self._collapsed for k in keys):
                for k in keys:
                    self._row_nodes[k].expand()
                self._collapsed.clear()
                self._expanded.update(k for k in keys if k[0] == "plan")
                self.refresh_all("unfolded all")
            else:
                for k in keys:
                    self._row_nodes[k].collapse()
                    self._collapsed.add(k)
                self._expanded.clear()
                self.refresh_all(f"folded {len(keys)} rows")

        def _children_of(self, kind: str, oid: int) -> list[tuple[str, int]]:
            """Visible child row keys, in tree order."""
            if kind == "plan":
                return [
                    ("milestone", s.id)
                    for s in self.store.list_milestones(oid)
                    if ("milestone", s.id) in self._row_nodes
                ]
            if kind == "milestone":
                return [
                    ("task", t.id)
                    for t in self.store.list_tasks(oid)
                    if ("task", t.id) in self._row_nodes
                ]
            return []

        def _parent_of(self, kind: str, oid: int) -> tuple[str, int] | None:
            if kind == "milestone":
                s = self.store.get_milestone(oid)
                return ("plan", s.plan_id) if s else None
            if kind == "task":
                t = self.store.get_task(oid)
                return ("milestone", t.milestone_id) if t else None
            return None

        def action_fold_left(self) -> None:
            """Left: collapse the header, else jump to its parent."""
            if self.selected is None:
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
                self._expanded.discard((kind, oid))
                self.refresh_all(f"{kind} #{oid} folded")
                return
            parent = self._parent_of(kind, oid)
            if parent is not None and parent in self._row_nodes:
                self.query_one("#tree", Tree).move_cursor(self._row_nodes[parent])

        def action_fold_right(self) -> None:
            """Right: expand the header, else jump to its first child."""
            if self.selected is None:
                return
            kind, oid = self.selected
            node = self._row_nodes.get(self.selected)
            if node is not None and (kind, oid) in self._collapsed:
                node.expand()
                self._collapsed.discard((kind, oid))
                if kind == "plan":
                    self._expanded.add((kind, oid))
                self.refresh_all(f"{kind} #{oid} unfolded")
                return
            for child in self._children_of(kind, oid):
                self.query_one("#tree", Tree).move_cursor(self._row_nodes[child])
                return

        # -- polling (fingerprint, not just mtime) ----------------------
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
        ) -> list[tuple[Plan, list[tuple[Milestone, list[Task]]]]]:
            if self.show_all or self.plan_filter is not None:
                return services.tree(
                    self.store, status=self.status_filter, plan_id=self.plan_filter
                )
            return services.tree(
                self.store, status=self.status_filter, limit=services.DEFAULT_PLAN_LIMIT
            )

        def refresh_all(self, note: str = "") -> None:
            tree = self.query_one("#tree", Tree)
            tree.clear()
            self._row_nodes = {}
            root = tree.root
            link_map = self.store.links_map()
            for p, milestones in self._filtered_tree():
                pn = root.add(
                    plan_row(p, links=link_map.get(("plan", p.id))),
                    data={"kind": "plan", "id": p.id},
                    allow_expand=bool(milestones),
                )
                self._row_nodes[("plan", p.id)] = pn
                for s, tasks in milestones:
                    sn = pn.add(
                        milestone_row(s, self.store, links=link_map.get(("milestone", s.id))),
                        data={"kind": "milestone", "id": s.id},
                        allow_expand=bool(tasks),
                    )
                    self._row_nodes[("milestone", s.id)] = sn
                    for t in tasks:
                        leaf = sn.add_leaf(
                            task_row(t, self.store, links=link_map.get(("task", t.id))),
                            data={"kind": "task", "id": t.id},
                        )
                        self._row_nodes[("task", t.id)] = leaf
            root.expand()
            self._collapsed &= set(self._row_nodes)  # drop rows deleted since last build
            self._expanded &= set(self._row_nodes)
            done_plans = {
                ("plan", p.id) for p, _ in self._filtered_tree() if p.status == Status.DONE
            }
            for key, node in self._row_nodes.items():
                if key in self._collapsed:
                    node.collapse()
                elif key in done_plans and key not in self._expanded:
                    node.collapse()
                    self._collapsed.add(key)
                elif node.allow_expand:
                    node.expand()
            c = self.store.counts()
            events = self.store.feed(1)
            act = ""
            if events:
                e = events[0]
                act = f"last: [{e['actor']}] {e['kind']}/{e['action']}: {e['detail']}"
            self.query_one("#activity", Label).update(" " + act)
            sf = self.status_filter.value if self.status_filter else "all"
            pf = f"P#{self.plan_filter}" if self.plan_filter else "all"
            self.query_one("#statusbar", Label).update(
                f" [{repo_label(self.store.path)}]"
                f" P:{c['plans']} S:{c['milestones']} T:{c['tasks_done']}/{c['tasks']}"
                f" Q:{c['plans_todo']}/{c['plans_doing']}/{c['plans_done']}"
                f" · f:{sf} o:{pf} A:{'all' if self.show_all else services.DEFAULT_PLAN_LIMIT}"
                + (f" — {note}" if note else "")
            )

        def action_refresh(self) -> None:
            self._saved("manual refresh")

        def _saved(self, note: str = "") -> None:
            """Refresh fingerprint + tree after a mutation."""
            self._fp = self.store.fingerprint()
            self.refresh_all(note)

        def action_filter_status(self) -> None:
            i = STATUS_CYCLE.index(self.status_filter)
            self.status_filter = STATUS_CYCLE[(i + 1) % len(STATUS_CYCLE)]
            self.refresh_all(
                f"status filter: {self.status_filter.value if self.status_filter else 'all'}"
            )

        def action_filter_plan(self) -> None:
            ids = [p.id for p in self.store.list_plans() if not services.is_archived(self.store, p)]
            order: list[int | None] = [None, *ids]
            try:
                i = order.index(self.plan_filter)
            except ValueError:
                i = 0
            self.plan_filter = order[(i + 1) % len(order)]
            self.refresh_all(f"plan filter: {self.plan_filter or 'all'}")

        def action_toggle_show_all(self) -> None:
            self.show_all = not self.show_all
            self.refresh_all("showing all plans" if self.show_all else "showing recent plans")

        def action_help(self) -> None:
            self.push_screen(HelpScreen())

        # -- editing ------------------------------------------------------
        def _milestone_for_task_ctx(self) -> int | None:
            if self.selected is None:
                return None
            kind, oid = self.selected
            if kind == "milestone":
                return oid
            if kind == "task":
                t = self.store.get_task(oid)
                return t.milestone_id if t else None
            return None

        def _plan_ctx(self) -> int | None:
            if self.plan_filter is not None:
                return self.plan_filter
            if self.selected is None:
                return None
            kind, oid = self.selected
            if kind == "plan":
                return oid
            if kind == "milestone":
                s = self.store.get_milestone(oid)
                return s.plan_id if s else None
            if kind == "task":
                t = self.store.get_task(oid)
                if t is None:
                    return None
                s = self.store.get_milestone(t.milestone_id)
                return s.plan_id if s else None
            return None

        def action_new_context(self) -> None:
            sid = self._milestone_for_task_ctx()
            if sid is not None:
                self.action_new_task()
                return
            pid = self._plan_ctx()
            if pid is not None:
                self.action_new_milestone()
                return
            self.action_new_plan()

        def action_new_plan(self) -> None:
            def cb(data: dict | None) -> None:
                if not data:
                    return
                try:
                    services.create_plan(
                        self.store,
                        data["title"],
                        data["what"],
                        goal=data["why"],
                        priority=data["priority"],
                        actor="tui",
                    )
                except ValueError as exc:
                    self.notify(f"error: {exc}")
                self._saved("plan created")

            self.push_screen(
                NewPlanScreen(defaults=load_template("plan", self.store.path).defaults), cb
            )

        def action_new_milestone(self) -> None:
            pid = self._plan_ctx()
            if pid is None:
                plans = self.store.list_plans()
                if not plans:
                    self.notify("no plans — press P to create one first")
                    return
                pid = plans[0].id

            def cb(data: dict | None) -> None:
                if not data:
                    return
                try:
                    services.create_milestone(
                        self.store,
                        pid,
                        data["title"],
                        data["desc"],
                        priority=data["priority"],
                        actor="tui",
                    )
                except (ValueError, KeyError) as exc:
                    self.notify(f"error: {exc}")
                self._saved("milestone created")

            self.push_screen(
                NewMilestoneScreen(
                    pid, defaults=load_template("milestone", self.store.path).defaults
                ),
                cb,
            )

        def action_new_task(self) -> None:
            sid = self._milestone_for_task_ctx()
            if sid is None:
                self.notify("select a milestone first (or press M to create one)")
                return

            def cb(data: dict | None) -> None:
                if not data:
                    return
                try:
                    services.create_task(
                        self.store,
                        sid,
                        data["title"],
                        data["desc"],
                        priority=data["priority"],
                        actor="tui",
                    )
                except (ValueError, KeyError) as exc:
                    self.notify(f"error: {exc}")
                self._saved("task created")

            self.push_screen(
                NewTaskScreen(sid, defaults=load_template("task", self.store.path).defaults), cb
            )

        def action_edit(self) -> None:
            if self.selected is None:
                self.notify("select a row first (j/k + click)")
                return
            kind, oid = self.selected
            obj: Plan | Milestone | Task | None = None
            if kind == "plan":
                obj = self.store.get_plan(oid)
                title = obj.name if obj else ""
            elif kind == "milestone":
                obj = self.store.get_milestone(oid)
                title = obj.title if obj else ""
            else:
                obj = self.store.get_task(oid)
                title = obj.title if obj else ""
            if obj is None:
                self.notify("selected row no longer exists — refreshing")
                self.refresh_all("")
                return
            details = obj.description
            priority = obj.priority

            def cb(data: dict | None) -> None:
                if not data:
                    return
                try:
                    if kind == "plan":
                        self.store.update_plan(
                            oid,
                            name=data["title"],
                            description=data["details"],
                            priority=data["priority"],
                            actor="tui",
                        )
                    elif kind == "milestone":
                        self.store.update_milestone(
                            oid,
                            title=data["title"],
                            description=data["details"],
                            priority=data["priority"],
                            actor="tui",
                        )
                    else:
                        self.store.update_task(
                            oid,
                            title=data["title"],
                            description=data["details"],
                            priority=data["priority"],
                            actor="tui",
                        )
                except ValueError as exc:
                    self.notify(f"error: {exc}")
                self._saved("saved")

            self.push_screen(EditScreen(kind, oid, title, details, priority), cb)

        def action_toggle_status(self) -> None:
            if self.selected is None:
                self.notify("select a row first (space cycles its status)")
                return
            kind, oid = self.selected
            left = self.store.open_criteria(kind, oid)
            current = self.store.get_parent(kind, oid)
            if left and (current is None or current.status != Status.DONE):
                # advisory only: warn, then proceed (flow first)
                self.notify(f"warning: {len(left)} open criteria — closing anyway", timeout=5)
            nxt = services.cycle_status(self.store, kind, oid, actor="tui")
            if nxt is None:
                self.notify("selected row no longer exists")
            self._saved(f"{kind} #{oid} -> {nxt.value if nxt else '?'}")

        def action_criteria(self) -> None:
            """Tick first open criterion; if none open, reopen the last done one."""
            if self.selected is None:
                self.notify("select a row first (c ticks criteria)")
                return
            kind, oid = self.selected
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
            verb = "reopened" if reopen else "checked"
            self._saved(f"criteria #{target.id} {verb}")

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
                self._saved(f"deleted {kind} #{oid}")

            self.push_screen(ConfirmScreen(f"Delete {kind} #{oid}?\n(children go too.)"), cb)

        def on_tree_node_selected(self, e: Tree.NodeSelected) -> None:
            """Clicks and cursor moves select only; enter/double-click open detail."""
            self._track(e.node)

        def note_click(self, key: tuple[str, int]) -> bool:
            """True when this click completes a double-click on the same row."""
            now = time.monotonic()
            double = (
                key == self._last_click_key and (now - self._last_click_at) < DOUBLE_CLICK_WINDOW
            )
            self._last_click_key, self._last_click_at = key, now
            return double

        def _open_detail(self, kind: str, oid: int) -> None:
            def cb(saved: bool | None) -> None:
                if saved:
                    self._saved("saved detail")

            self.push_screen(DetailScreen(self.store, kind, oid), cb)

        def action_open_detail(self) -> None:
            if len(self.screen_stack) > 1:
                return  # a modal owns enter
            if self.selected is None:
                self.notify("select a row first, then enter")
                return
            self._open_detail(*self.selected)

    def create_app(db_path: str | None = None) -> LazyplanApp:
        """Build the app bound to a store."""
        return LazyplanApp(Store(db_path))


def run(db_path: str | None = None) -> int:
    """Run the TUI; exit 3 when Textual is missing."""
    if not _TEXTUAL_OK:
        print("Textual not installed. Run: pip install -e . then: lpui ui")
        print("Fallback (no TUI): lpui list")
        return 3
    create_app(db_path).run()
    return 0
