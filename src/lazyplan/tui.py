"""Modal-palette Textual TUI: nav tree + live preview, one status line.

Keys: j/k navigate, left/right fold, enter detail, c palette,
  escape clear. Press c then type a prefix (new, cycle, tick,
  fold, filter, ...) and enter runs the match.
  Mouse click selects; double-click opens detail.
Keyboard-only: agents use the `lpui` CLI against the same SQLite file; local edits
bump reactive rev, external DB changes arrive via fingerprint() poll + feed toast.
"""

from __future__ import annotations

import time
from typing import Any, cast

try:
    from textual import events, on
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.reactive import reactive
    from textual.widgets import Label, Static, Tree
    from textual.widgets.tree import TreeNode

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from . import services
from .cli_parser import package_version
from .design import (
    APP_CSS,
    EMPTY_FEED,
    EMPTY_NO_PLANS,
    milestone_row,
    plan_row,
    task_row,
)
from .messages import RowAction, SelectionChanged
from .models import Milestone, Plan, Status, Task
from .repo import repo_label
from .screens import (
    ConfirmScreen,
    DetailScreen,
    FilterPromptScreen,
    HelpScreen,
    NewMilestoneScreen,
    NewPlanScreen,
    NewTaskScreen,
    PaletteScreen,
)
from .store import Store
from .templates import load_template
from .upgrade import UpgradeError, detect, latest_version, notice_text

STATUS_CYCLE: list[Status | None] = [None, Status.TODO, Status.DOING, Status.DONE]
DOUBLE_CLICK_WINDOW = 0.5  # seconds between two clicks on one row

if _TEXTUAL_OK:

    class FoldTree(Tree):
        """Plan/milestone tree: j/k + arrows move, enter opens detail.

        Minimal keys own the tree; every mutation runs through the modal
        palette (c). Native Tree space/shift+space are parked
        here so they do nothing — status and folding live in the palette.
        """

        BINDINGS = [Binding("enter", "open_detail", "Detail")]

        def on_tree_node_highlighted(self, e: Tree.NodeHighlighted) -> None:
            """Bubble selection as a custom message (guide/events pattern)."""
            key = LazyplanApp._node_key(e.node)
            if key is not None:
                self.post_message(SelectionChanged(kind=key[0], oid=key[1]))

        def action_toggle_node(self) -> None:
            """Space: parked — use the modal palette for status changes."""
            return

        def action_toggle_expand_all(self) -> None:
            """Shift+space: parked — use the modal palette for folding."""
            return

        def action_open_detail(self) -> None:
            """Enter: post intent; App handles via @on."""
            app = cast("LazyplanApp", self.app)
            if app.selected is not None:
                kind, oid = app.selected
                self.post_message(RowAction("open-detail", kind, oid))
            else:
                app.action_open_detail()

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
            if key is None:
                return
            # Messages-up: announce selection, then open on double-click.
            self.post_message(SelectionChanged(kind=key[0], oid=key[1]))
            if app.note_click(key):
                self.post_message(RowAction("open-detail", key[0], key[1]))

    class LazyplanApp(App):
        """Single-panel TUI: the plan tree."""

        TITLE = "lazyplan"
        CSS = APP_CSS
        ENABLE_COMMAND_PALETTE = False
        BINDINGS = [
            Binding("j", "cursor_down", "Down", show=False),
            Binding("k", "cursor_up", "Up", show=False),
            Binding("enter", "open_detail", "Detail"),
            Binding("left", "fold_left", "Fold", show=False),
            Binding("right", "fold_right", "Unfold", show=False),
            Binding("escape", "clear_filter", "Clear", show=False),
            Binding("c", "command_palette", "Palette"),
        ]

        def __init__(self, store: Store) -> None:
            super().__init__()
            self.store = store
            self.selected: tuple[str, int] | None = None
            self.status_filter: Status | None = None
            self.show_all: bool = False
            self.filter_text: str = ""
            self._row_nodes: dict[tuple[str, int], TreeNode] = {}
            self._collapsed: set[tuple[str, int]] = set()
            self._expanded: set[tuple[str, int]] = set()
            self._last_click_key: tuple[str, int] | None = None
            self._last_click_at: float = 0.0
            self._fp: Any = store.fingerprint()
            self._update_notice: str | None = None
            self._update_toasted: bool = False
            self._pending_note: str = ""
            self._mounted: bool = False

        # Reactive revision: local mutations bump rev; watch_rev refreshes.
        # External CLI writes still arrive via _poll fingerprint check.
        rev = reactive(0, init=False)

        def watch_rev(self, _old: int, _new: int) -> None:
            if not self._mounted:
                return
            try:
                self._fp = self.store.fingerprint()
            except Exception:
                pass
            note = self._pending_note
            self._pending_note = ""
            try:
                self.refresh_all(note)
            except Exception:
                pass

        def compose(self) -> ComposeResult:
            with Vertical(id="panel"):
                with Horizontal(id="main"):
                    with Vertical(id="nav"):
                        yield FoldTree("plans", id="tree")
                    with VerticalScroll(id="preview"):
                        yield Static("", id="preview-body")
            yield Label("", id="status")

        def on_mount(self) -> None:
            self._mounted = True
            self.refresh_all("ready — c for commands")
            self.set_interval(1.0, self._poll)
            self.run_worker(self._check_update, thread=True, exclusive=True)
            self.query_one("#tree", Tree).focus()

        def _check_update(self) -> None:
            """One background latest-version check per session; silent on failure."""
            try:
                latest = latest_version()
            except UpgradeError:
                return
            notice = notice_text(detect(), package_version(), latest)
            if notice is not None:
                self.call_from_thread(self._announce_update, notice)

        def _announce_update(self, notice: str) -> None:
            self._update_notice = notice
            if not self._update_toasted:
                self._update_toasted = True
                self.notify(notice, timeout=8)
            self.refresh_all()

        # -- selection --------------------------------------------------
        def _track(self, node: TreeNode) -> None:
            data = getattr(node, "data", None)
            if isinstance(data, dict) and "kind" in data and "id" in data:
                self.selected = (data["kind"], int(data["id"]))
                self.update_preview()

        def on_tree_node_highlighted(self, e: Tree.NodeHighlighted) -> None:
            self._track(e.node)

        @on(SelectionChanged)
        def _on_selection_changed(self, e: SelectionChanged) -> None:
            """Custom message (bubbles FoldTree -> App): track cursor."""
            self.selected = (e.kind, e.oid)
            self.update_preview()

        def update_preview(self) -> None:
            """Reactive preview: render selected row without modal."""
            try:
                body = self.query_one("#preview-body", Static)
            except Exception:
                return
            try:
                total_plans = self.store.counts()["plans"]
            except Exception:
                total_plans = 1
            if total_plans == 0:
                body.update(EMPTY_NO_PLANS)
                return
            if self.selected is None:
                body.update("select a row (j/k + click) — preview appears here")
                return
            kind, oid = self.selected
            try:
                full = self.store.get_full(kind, oid)
            except Exception:
                body.update(f"{kind} #{oid} — gone, press r")
                return
            if full is None:
                body.update(f"{kind} #{oid} — gone, press r")
                return
            obj_key = {"plan": "plan", "milestone": "milestone", "task": "task"}[kind]
            obj = full.get(obj_key, {})
            title = str(obj.get("title", obj.get("name", "")))
            status = str(obj.get("status", ""))
            desc = str(obj.get("description", "") or "")
            goal = str(obj.get("goal", "") or "") if kind == "plan" else ""
            crits = full.get("criteria", [])
            done = sum(1 for c in crits if c.get("done"))
            lines = [f"{kind} #{oid} [{status}]", title]
            if goal:
                lines.append(f"why: {goal}")
            if desc:
                lines.extend(["", *desc.splitlines()[:10]])
            if crits:
                lines.append("")
                lines.append(f"acceptance {done}/{len(crits)}:")
                for c in crits[:10]:
                    mark = "x" if c.get("done") else " "
                    lines.append(f"[{mark}] #{c.get('id')} {c.get('text')}")
            links = full.get("links", [])
            if links:
                lines.append("")
                lines.append(f"commits: {len(links)} linked")
            repos = full.get("effective_repos") or full.get("repos") or []
            if repos:
                names = [str(r.get("repo_path", "")) for r in repos[:3]]
                lines.append(f"repos: {', '.join(names)}")
            if kind == "plan":
                ms = full.get("milestones", [])
                tcount = sum(len(e.get("tasks", [])) for e in ms)
                lines.append("")
                lines.append(f"{len(ms)} milestones, {tcount} tasks — enter for detail")
            body.update("\n".join(lines))

        @on(RowAction)
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
            """External-change detector; local edits go through rev."""
            try:
                fp = self.store.fingerprint()
            except Exception:
                return
            if fp != self._fp:
                events_ = self.store.feed(1)
                note = "db changed — refreshed"
                if events_:
                    e = events_[0]
                    note = f"[{e['actor']}] {e['kind']}/{e['action']}: {e['detail']}"
                    try:
                        self.notify(note, timeout=4)
                    except Exception:
                        pass
                self._pending_note = note
                self.rev += 1

        # -- rendering ---------------------------------------------------
        def _filtered_tree(
            self,
        ) -> list[tuple[Plan, list[tuple[Milestone, list[Task]]]]]:
            if self.show_all or self.filter_text.strip():
                base = services.tree(self.store, status=self.status_filter)
            else:
                base = services.tree(
                    self.store, status=self.status_filter, limit=services.DEFAULT_PLAN_LIMIT
                )
            query = self.filter_text.strip().lower()
            if not query:
                return base
            filtered: list[tuple[Plan, list[tuple[Milestone, list[Task]]]]] = []
            for p, milestones in base:
                if query in p.name.lower():
                    filtered.append((p, milestones))
                    continue
                kept_ms: list[tuple[Milestone, list[Task]]] = []
                for s, tasks in milestones:
                    if query in s.title.lower():
                        kept_ms.append((s, list(tasks)))
                        continue
                    hits = [t for t in tasks if query in t.title.lower()]
                    if hits:
                        kept_ms.append((s, hits))
                if kept_ms:
                    filtered.append((p, kept_ms))
            return filtered

        def action_clear_filter(self) -> None:
            if len(self.screen_stack) > 1:
                return
            if self.filter_text:
                self.filter_text = ""
                self._pending_note = "filter cleared"
                try:
                    self.rev += 1
                except Exception:
                    self.refresh_all("filter cleared")
                try:
                    self.query_one("#tree", Tree).focus()
                except Exception:
                    pass

        def refresh_all(self, note: str = "") -> None:
            tree = self.query_one("#tree", Tree)
            prev_selected = self.selected
            prev_cursor = None
            try:
                cur = tree.cursor_node
                if cur is not None:
                    prev_cursor = self._node_key(cur)
            except Exception:
                pass
            tree.clear()
            self._row_nodes = {}
            root = tree.root
            link_map = self.store.links_map()
            repos_map = self.store.repos_map()
            filtered = self._filtered_tree()
            for p, milestones in filtered:
                pn = root.add(
                    plan_row(
                        p,
                        links=link_map.get(("plan", p.id)),
                        repos=repos_map.get(("plan", p.id)),
                    ),
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
            done_plans = {("plan", p.id) for p, _ in filtered if p.status == Status.DONE}
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
            if events:
                e = events[0]
                act = f"last: [{e['actor']}] {e['kind']}/{e['action']}: {e['detail']}"
            else:
                act = EMPTY_FEED
            sf = self.status_filter.value if self.status_filter else "all"
            shown_plans = len(self._row_nodes and [k for k in self._row_nodes if k[0] == "plan"] or [])
            bar = (
                f" [{repo_label(self.store.path)}]"
                f" P:{c['plans']} S:{c['milestones']} T:{c['tasks_done']}/{c['tasks']}"
                f" Q:{c['plans_todo']}/{c['plans_doing']}/{c['plans_done']}"
                f" · f:{sf} A:{'all' if self.show_all else services.DEFAULT_PLAN_LIMIT}"
            )
            if self.filter_text.strip():
                bar += f" · /{self.filter_text.strip()} ({shown_plans} plans)"
            if self._update_notice is not None:
                bar += f" · {self._update_notice}"
            if note:
                bar += f" — {note}"
            self.query_one("#status", Label).update(f"{bar} · {act}")
            # -- focus/collapse preservation (keyboard-nav polish) --
            target = prev_selected if prev_selected in self._row_nodes else prev_cursor
            if target not in self._row_nodes:
                target = None
            if target is None and self._row_nodes:
                # keep selection valid: first visible plan, else first row
                for k in self._row_nodes:
                    if k[0] == "plan":
                        target = k
                        break
                if target is None:
                    target = next(iter(self._row_nodes))
                self.selected = target
            if target in self._row_nodes:
                node = self._row_nodes[target]
                try:
                    tree.move_cursor(node)
                except Exception:
                    pass

                def _restore(n=node) -> None:
                    try:
                        tree.move_cursor(n)
                        tree.scroll_to_node(n)
                    except Exception:
                        pass

                try:
                    self.call_after_refresh(_restore)
                except Exception:
                    pass
            self.update_preview()

        def action_refresh(self) -> None:
            self._saved("manual refresh")

        def _saved(self, note: str = "") -> None:
            """Local mutation path: bump reactive rev, watch refreshes."""
            self._pending_note = note
            try:
                self.rev += 1
            except Exception:
                self._fp = self.store.fingerprint()
                self.refresh_all(note)

        def action_filter_status(self) -> None:
            i = STATUS_CYCLE.index(self.status_filter)
            self.status_filter = STATUS_CYCLE[(i + 1) % len(STATUS_CYCLE)]
            self.refresh_all(
                f"status filter: {self.status_filter.value if self.status_filter else 'all'}"
            )

        def action_toggle_show_all(self) -> None:
            self.show_all = not self.show_all
            self.refresh_all("showing all plans" if self.show_all else "showing recent plans")

        def action_help(self) -> None:
            self.push_screen(HelpScreen())

        def action_command_palette(self) -> None:
            """Open the modal command palette (c)."""
            if len(self.screen_stack) > 1:
                return
            self.push_screen(PaletteScreen(), self._run_palette_command)

        def _open_filter_prompt(self) -> None:
            """Prompt for tree filter text; empty clears the filter."""

            def cb(text: str | None) -> None:
                if text is None:
                    return
                self.filter_text = text
                self._pending_note = f"filter: {text}" if text else "filter cleared"
                try:
                    self.rev += 1
                except Exception:
                    self.refresh_all(self._pending_note)

            self.push_screen(FilterPromptScreen(), cb)

        def _run_palette_command(self, cmd: str | None) -> None:
            """Run one palette command id from the modal palette."""
            if not cmd:
                return
            if cmd == "filter-text":
                self._open_filter_prompt()
                return
            try:
                self.store.feed(0)
            except Exception:
                pass
            dispatch = {
                "create": self.action_new_context,
                "open-detail": self.action_open_detail,
                "export-md": self.action_export_md,
                "criteria": self.action_criteria,
                "delete": self.action_delete,
                "toggle-status": self.action_toggle_status,
                "fold": self.action_fold,
                "fold-all": self.action_fold_all,
                "filter": self.action_filter_status,
                "show-all": self.action_toggle_show_all,
                "refresh": self.action_refresh,
                "help": self.action_help,
                "quit": self.action_quit if hasattr(self, "action_quit") else self.exit,
            }
            fn = dispatch.get(cmd)
            if fn is not None:
                fn()
                self._pending_note = f"palette: {cmd}"
                # actor trail: palette runs are TUI writes
                try:
                    self._fp = self.store.fingerprint()
                except Exception:
                    pass

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

        def _cursor_is_root(self) -> bool:
            """True when the cursor sits on the dataless plans root or empty tree."""
            try:
                tree = self.query_one("#tree", Tree)
            except Exception:
                return True
            try:
                cur = tree.cursor_node
            except Exception:
                return True
            if cur is None:
                return True
            return self._node_key(cur) is None

        def action_new_context(self) -> None:
            if self._cursor_is_root():
                self.action_new_plan()
                return
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
                self.notify("select a plan first (j/k + click)")
                return

            def cb(data: dict | None) -> None:
                if not data:
                    return
                try:
                    services.create_milestone(
                        self.store,
                        pid,
                        data["title"],
                        data["desc"],
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
                        actor="tui",
                    )
                except (ValueError, KeyError) as exc:
                    self.notify(f"error: {exc}")
                self._saved("task created")

            self.push_screen(
                NewTaskScreen(sid, defaults=load_template("task", self.store.path).defaults), cb
            )

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

        def action_export_md(self) -> None:
            pid = self._plan_ctx()
            if pid is None:
                self.notify("select a row first, then export")
                return
            entry = services.export_plan(self.store, pid)
            if entry is None:
                self.notify("selected plan no longer exists — refreshing")
                self.refresh_all("")
                return
            from .render import render_plan_markdown

            path = f"plan-P{pid}.md"
            with open(path, "w") as fh:
                fh.write(render_plan_markdown(entry) + "\n")
            self._saved(f"exported {path}")

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
