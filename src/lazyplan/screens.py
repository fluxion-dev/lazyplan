"""TUI screens: modal forms, pickers, and detail views.

The app shell (LazyplanApp) lives in tui.py; every overlay lives here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

try:
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.containers import Vertical
    from textual.screen import ModalScreen
    from textual.widgets import Button, Checkbox, Input, Label, OptionList, Static, TextArea

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from .design import HELP_TEXT, msg_error, project_label, story_label, task_label

if TYPE_CHECKING:
    from .store import Store

if _TEXTUAL_OK:

    class _Form(ModalScreen):
        """Modal base; dialog chrome comes from design.APP_CSS.

        Esc backs out of every form without saving (matches the Cancel
        button); per-screen callbacks already treat a None result as cancel.
        """

        BINDINGS = [Binding("escape", "cancel", "Cancel")]

        def action_cancel(self) -> None:
            """Return to the previous screen, discarding edits."""
            self.dismiss(None)

    class NewProjectScreen(_Form):
        """Create-project form."""

        def compose(self) -> ComposeResult:
            with Vertical(id="dlg"):
                yield Label("New project  (opens as P#...)")
                yield Input(placeholder="name *", id="f-name")
                yield Input(placeholder="description", id="f-desc")
                yield Input(placeholder="start YYYY-MM-DD", id="f-start")
                yield Input(placeholder="end YYYY-MM-DD", id="f-end")
                yield Button("Create", id="ok")
                yield Button("Cancel", id="cancel")

        def on_button_pressed(self, e: Button.Pressed) -> None:
            if e.button.id == "ok":
                self.dismiss(
                    {
                        k: self.query_one(f"#f-{k}", Input).value.strip()
                        for k in ("name", "desc", "start", "end")
                    }
                )
            else:
                self.dismiss(None)

    class NewStoryScreen(_Form):
        """Create-story form for one project."""

        def __init__(self, project_id: int) -> None:
            super().__init__()
            self.project_id = project_id

        def compose(self) -> ComposeResult:
            with Vertical(id="dlg"):
                yield Label(f"New story in P#{self.project_id}")
                yield Input(placeholder="title *", id="f-title")
                yield Input(placeholder="description", id="f-desc")
                yield Input(placeholder="start YYYY-MM-DD", id="f-start")
                yield Input(placeholder="end YYYY-MM-DD", id="f-end")
                yield Button("Create", id="ok")
                yield Button("Cancel", id="cancel")

        def on_button_pressed(self, e: Button.Pressed) -> None:
            if e.button.id == "ok":
                self.dismiss(
                    {
                        k: self.query_one(f"#f-{k}", Input).value.strip()
                        for k in ("title", "desc", "start", "end")
                    }
                )
            else:
                self.dismiss(None)

    class NewTaskScreen(_Form):
        """Create-task form for one story."""

        def __init__(self, story_id: int) -> None:
            super().__init__()
            self.story_id = story_id

        def compose(self) -> ComposeResult:
            with Vertical(id="dlg"):
                yield Label(f"New task in S#{self.story_id}")
                yield Input(placeholder="title *", id="f-title")
                yield Input(placeholder="estimate (e.g. 2d)", id="f-est")
                yield Input(placeholder="start YYYY-MM-DD", id="f-start")
                yield Input(placeholder="end YYYY-MM-DD", id="f-end")
                yield Button("Create", id="ok")
                yield Button("Cancel", id="cancel")

        def on_button_pressed(self, e: Button.Pressed) -> None:
            if e.button.id == "ok":
                self.dismiss(
                    {
                        k: self.query_one(f"#f-{k}", Input).value.strip()
                        for k in ("title", "est", "start", "end")
                    }
                )
            else:
                self.dismiss(None)

    class EditScreen(_Form):
        """Edit title plus desc/estimate (and owner on stories/tasks)."""

        def __init__(self, kind: str, obj_id: int, title: str, extra: str, owner: str = "") -> None:
            super().__init__()
            self.kind, self.obj_id, self.title, self.extra, self.owner = (
                kind,
                obj_id,
                title,
                extra,
                owner,
            )

        def compose(self) -> ComposeResult:
            with Vertical(id="dlg"):
                yield Label(f"Edit {self.kind} #{self.obj_id}")
                yield Input(value=self.title, id="f-title")
                yield Input(
                    value=self.extra,
                    placeholder="desc (project/story) or estimate (task)",
                    id="f-extra",
                )
                if self.kind in ("story", "task"):
                    yield Input(
                        value=self.owner, placeholder="owner (person or agent id)", id="f-owner"
                    )
                yield Button("Save", id="ok")
                yield Button("Cancel", id="cancel")

        def on_button_pressed(self, e: Button.Pressed) -> None:
            if e.button.id == "ok":
                data: dict[str, str] = {
                    "title": self.query_one("#f-title", Input).value,
                    "extra": self.query_one("#f-extra", Input).value,
                }
                if self.kind in ("story", "task"):
                    data["owner"] = self.query_one("#f-owner", Input).value.strip()
                self.dismiss(data)
            else:
                self.dismiss(None)

    def _fuzzy_score(query: str, text: str) -> int | None:
        """Subsequence match score (lower is better), None if no match."""
        q, t = query.lower(), text.lower()
        pos, score = 0, 0
        for ch in q:
            nxt = t.find(ch, pos)
            if nxt < 0:
                return None
            score += nxt - pos
            pos = nxt + 1
        return score

    class _PickScreen(_Form):
        """Shared jump-to-row modal: palette (fuzzy + commands) subclasses it."""

        def __init__(self, title: str, items: list[tuple[str, str, str]]) -> None:
            super().__init__()
            self._pick_title = title
            self._pick_items = items  # (label, kind, ref)

        def compose(self) -> ComposeResult:
            from textual.widgets import Input as _Input
            from textual.widgets import Label as _Label
            from textual.widgets import OptionList as _OL

            with Vertical(id="dlg"):
                yield _Label(self._pick_title)
                yield _Input(
                    placeholder="type to filter — enter jumps, esc cancels", id="pick-filter"
                )
                yield _OL(id="pick-list")

        def on_mount(self) -> None:
            from textual.widgets import Input as _Input

            self.query_one("#pick-filter", _Input).focus()
            self._show(self._pick_items)

        def _show(self, items: list[tuple[str, str, str]]) -> None:
            from textual.widgets import OptionList as _OL
            from textual.widgets._option_list import Option as _Option

            lst = self.query_one("#pick-list", _OL)
            lst.clear_options()
            for label, kind, ref in items[:60]:
                lst.add_option(_Option(label, id=f"{kind}:{ref}"))

        def filter_items(self, query: str) -> list[tuple[str, str, str]]:
            """Subclasses implement matching."""
            raise NotImplementedError

        def on_input_changed(self, event: Input.Changed) -> None:
            if event.input.id == "pick-filter":
                self._show(self.filter_items(event.value.strip()))

        def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
            oid = event.option_id or ""
            kind, _, ref = oid.partition(":")
            self.dismiss((kind, ref))

    class PaletteScreen(_PickScreen):
        def __init__(self, store: Store) -> None:
            items: list[tuple[str, str, str]] = [
                ("tree view", "cmd", "tree"),
                ("gantt view", "cmd", "gantt"),
                ("feed view", "cmd", "feed"),
                ("proposals view", "cmd", "props"),
                ("help", "cmd", "help"),
            ]
            for p, stories in store.tree():
                items.append((project_label(p), "project", str(p.id)))
                for s, tasks in stories:
                    items.append((f"  {story_label(s, store)}", "story", str(s.id)))
                    for t in tasks:
                        items.append((f"    {task_label(t, store)}", "task", str(t.id)))
            super().__init__("Palette (Ctrl-P) — rows + commands", items)

        def filter_items(self, query: str) -> list[tuple[str, str, str]]:
            """Fuzzy subsequence match, best first."""
            if not query:
                return self._pick_items
            scored = []
            for label, kind, ref in self._pick_items:
                score = _fuzzy_score(query, label)
                if score is not None:
                    scored.append((score, label, kind, ref))
            scored.sort()
            return [(label, kind, ref) for _, label, kind, ref in scored]

    class SearchScreen(_PickScreen):
        def __init__(self, store: Store) -> None:
            items: list[tuple[str, str, str]] = []
            for p, stories in store.tree():
                items.append((project_label(p), "project", str(p.id)))
                for s, tasks in stories:
                    items.append((story_label(s, store), "story", str(s.id)))
                    for t in tasks:
                        items.append((task_label(t, store), "task", str(t.id)))
            super().__init__("Search (s) — jump to match", items)

        def filter_items(self, query: str) -> list[tuple[str, str, str]]:
            """Case-insensitive substring match."""
            if not query:
                return self._pick_items
            q = query.lower()
            return [
                (label, kind, ref) for label, kind, ref in self._pick_items if q in label.lower()
            ]

    class ConfirmScreen(_Form):
        """Delete confirmation; dismisses True on Delete."""

        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

        def compose(self) -> ComposeResult:
            with Vertical(id="dlg"):
                yield Static(self.text, markup=False)
                yield Button("Delete", id="ok", variant="error")
                yield Button("Cancel", id="cancel")

        def on_button_pressed(self, e: Button.Pressed) -> None:
            self.dismiss(e.button.id == "ok")

    class DetailScreen(_Form):
        """Editable detail (T#11): fields + interactive criteria checkboxes."""

        def __init__(self, store: Store, kind: str, oid: int) -> None:
            super().__init__()
            self._dstore = store
            self.dkind, self.doid = kind, oid
            self._crit_ids: list[int] = []

        def compose(self) -> ComposeResult:
            yield Label(f"{self.dkind} #{self.doid} — edit in place, Save writes")
            yield Input(placeholder="title", id="d-title")
            yield TextArea(id="d-desc")
            with Vertical(id="d-meta"):
                yield Input(placeholder="owner", id="d-owner")
                yield Input(placeholder="estimate", id="d-est")
                yield Input(placeholder="priority p0..p3 (empty clears)", id="d-pri")
                yield Input(placeholder="labels, comma,separated", id="d-labels")
                yield Input(placeholder="start YYYY-MM-DD", id="d-start")
                yield Input(placeholder="end YYYY-MM-DD", id="d-end")
                yield Input(placeholder="blocked by (ids, comma)", id="d-blocked")
            with Vertical(id="d-narr"):
                for fid, ph in (
                    ("d-goal", "goal"),
                    ("d-metrics", "success metrics"),
                    ("d-scope-in", "in scope"),
                    ("d-scope-out", "out of scope"),
                    ("d-assumes", "assumptions"),
                ):
                    yield Input(placeholder=ph, id=fid)
            with Vertical(id="d-crit"):
                yield Label("acceptance (tick = done):")
            yield Button("Save", id="ok", variant="primary")
            yield Button("Cancel", id="cancel")

        def on_mount(self) -> None:
            full = self._dstore.get_full(self.dkind, self.doid)
            if full is None:
                self.dismiss(None)
                return
            obj = full[{"project": "project", "story": "story", "task": "task"}[self.dkind]]
            self.query_one("#d-title", Input).value = str(obj.get("title", obj.get("name", "")))
            self.query_one("#d-desc", TextArea).text = str(obj.get("description", ""))
            is_proj = self.dkind == "project"
            self.query_one("#d-meta", Vertical).display = not is_proj
            self.query_one("#d-narr", Vertical).display = is_proj
            for fid, key in (
                ("#d-owner", "owner"),
                ("#d-est", "estimate"),
                ("#d-pri", "priority"),
                ("#d-start", "start_date"),
                ("#d-end", "end_date"),
                ("#d-blocked", "blocked_by"),
                ("#d-goal", "goal"),
                ("#d-metrics", "success_metrics"),
                ("#d-scope-in", "scope_in"),
                ("#d-scope-out", "scope_out"),
                ("#d-assumes", "assumptions"),
            ):
                val = obj.get(key, "")
                if isinstance(val, list):
                    val = ",".join(str(v) for v in val)
                self.query_one(fid, Input).value = str(val)
            self.query_one("#d-labels", Input).value = ",".join(obj.get("labels", []) or [])
            crit_box = self.query_one("#d-crit", Vertical)
            crits = full.get("criteria", [])
            if self.dkind == "project" or not crits:
                crit_box.display = False
            for c in crits:
                self._crit_ids.append(int(c["id"]))
                crit_box.mount(
                    Checkbox(f"#{c['id']} {c['text']}", value=bool(c["done"]), id=f"crit-{c['id']}")
                )

        def _input(self, selector: str) -> str:
            return self.query_one(selector, Input).value

        def on_button_pressed(self, e: Button.Pressed) -> None:
            if e.button.id != "ok":
                self.dismiss(None)
                return
            store = self._dstore
            title = self.query_one("#d-title", Input).value
            desc = self.query_one("#d-desc", TextArea).text
            try:
                if self.dkind == "project":
                    store.update_project(
                        self.doid,
                        name=title or None,
                        description=desc,
                        start_date=self._input("#d-start") or None,
                        end_date=self._input("#d-end") or None,
                        goal=self._input("#d-goal") or None,
                        success_metrics=self._input("#d-metrics") or None,
                        scope_in=self._input("#d-scope-in") or None,
                        scope_out=self._input("#d-scope-out") or None,
                        assumptions=self._input("#d-assumes") or None,
                        actor="tui",
                    )
                else:
                    fields: dict[str, str | None] = dict(
                        title=title or None,
                        description=desc,
                        estimate=self._input("#d-est") or None,
                        start_date=self._input("#d-start") or None,
                        end_date=self._input("#d-end") or None,
                        owner=self._input("#d-owner").strip() or None,
                        labels=self._input("#d-labels") or None,
                        blocked_by=self._input("#d-blocked") or None,
                    )
                    pri = self._input("#d-pri").strip()
                    if pri:
                        fields["priority"] = pri
                    for cid in self._crit_ids:
                        box = self.query_one(f"#crit-{cid}", Checkbox)
                        store.set_criteria(cid, box.value, actor="tui")
                    if self.dkind == "story":
                        store.update_story(
                            self.doid,
                            title=fields["title"],
                            description=fields["description"],
                            start_date=fields["start_date"],
                            end_date=fields["end_date"],
                            owner=fields["owner"],
                            labels=fields["labels"],
                            blocked_by=fields["blocked_by"],
                            priority=fields.get("priority"),
                            actor="tui",
                        )
                    else:
                        store.update_task(
                            self.doid,
                            title=fields["title"],
                            description=fields["description"],
                            estimate=fields["estimate"],
                            start_date=fields["start_date"],
                            end_date=fields["end_date"],
                            owner=fields["owner"],
                            labels=fields["labels"],
                            blocked_by=fields["blocked_by"],
                            priority=fields.get("priority"),
                            actor="tui",
                        )
            except ValueError as exc:
                self.notify(msg_error(exc))
                return
            self.dismiss(True)

    class HelpScreen(_Form):
        """Shared help text overlay; same source as `lp help`."""

        HELP = HELP_TEXT

        def compose(self) -> ComposeResult:
            with Vertical(id="dlg"):
                yield Static(self.HELP, markup=False)
                yield Button("Close", id="cancel")

        def on_button_pressed(self, e: Button.Pressed) -> None:
            self.dismiss(None)
