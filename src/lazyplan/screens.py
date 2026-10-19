"""TUI screens: modal forms and detail views.

The app shell (LazyplanApp) lives in tui.py; every overlay lives here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

try:
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.containers import Vertical
    from textual.screen import ModalScreen
    from textual.widgets import Button, Checkbox, Input, Label, Static, TextArea

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from .design import HELP_TEXT, msg_error
from .render import render_commits

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
        """Create-project form: title + priority + why + what."""

        def compose(self) -> ComposeResult:
            with Vertical(id="dlg"):
                yield Label("New project  (opens as P#...)")
                yield Input(placeholder="title *", id="f-title")
                yield Input(placeholder="priority p0..p3", id="f-priority")
                yield Input(placeholder="why does this exist?", id="f-why")
                yield Input(placeholder="what gets built?", id="f-what")
                yield Button("Create", id="ok")
                yield Button("Cancel", id="cancel")

        def on_button_pressed(self, e: Button.Pressed) -> None:
            if e.button.id == "ok":
                self.dismiss(
                    {
                        k: self.query_one(f"#f-{k}", Input).value.strip()
                        for k in ("title", "priority", "why", "what")
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
                yield Input(placeholder="priority p0..p3", id="f-priority")
                yield Input(placeholder="details", id="f-desc")
                yield Button("Create", id="ok")
                yield Button("Cancel", id="cancel")

        def on_button_pressed(self, e: Button.Pressed) -> None:
            if e.button.id == "ok":
                self.dismiss(
                    {
                        k: self.query_one(f"#f-{k}", Input).value.strip()
                        for k in ("title", "priority", "desc")
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
                yield Input(placeholder="priority p0..p3", id="f-priority")
                yield Input(placeholder="details", id="f-desc")
                yield Button("Create", id="ok")
                yield Button("Cancel", id="cancel")

        def on_button_pressed(self, e: Button.Pressed) -> None:
            if e.button.id == "ok":
                self.dismiss(
                    {
                        k: self.query_one(f"#f-{k}", Input).value.strip()
                        for k in ("title", "priority", "desc")
                    }
                )
            else:
                self.dismiss(None)

    class EditScreen(_Form):
        """Edit title + details + priority."""

        def __init__(self, kind: str, obj_id: int, title: str, details: str, priority: str) -> None:
            super().__init__()
            self.kind, self.obj_id, self.title, self.details, self.priority = (
                kind,
                obj_id,
                title,
                details,
                priority,
            )

        def compose(self) -> ComposeResult:
            with Vertical(id="dlg"):
                yield Label(f"Edit {self.kind} #{self.obj_id}")
                yield Input(value=self.title, id="f-title")
                yield Input(value=self.details, placeholder="details", id="f-details")
                yield Input(
                    value=self.priority, placeholder="priority p0..p3 (empty clears)", id="f-pri"
                )
                yield Button("Save", id="ok")
                yield Button("Cancel", id="cancel")

        def on_button_pressed(self, e: Button.Pressed) -> None:
            if e.button.id == "ok":
                self.dismiss(
                    {
                        "title": self.query_one("#f-title", Input).value,
                        "details": self.query_one("#f-details", Input).value,
                        "priority": self.query_one("#f-pri", Input).value.strip(),
                    }
                )
            else:
                self.dismiss(None)

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
        """Editable detail: fields + interactive criteria checkboxes."""

        def __init__(self, store: Store, kind: str, oid: int) -> None:
            super().__init__()
            self._dstore = store
            self.dkind, self.doid = kind, oid
            self._crit_ids: list[int] = []

        def compose(self) -> ComposeResult:
            yield Label(f"{self.dkind} #{self.doid} — edit in place, Save writes")
            yield Input(placeholder="title", id="d-title")
            yield TextArea(id="d-desc")
            yield Input(placeholder="priority p0..p3 (empty clears)", id="d-pri")
            with Vertical(id="d-why-box"):
                yield Input(placeholder="why does this exist?", id="d-why")
            with Vertical(id="d-crit"):
                yield Label("acceptance (tick = done):")
            with Vertical(id="d-commits"):
                yield Label("commits:")
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
            self.query_one("#d-pri", Input).value = str(obj.get("priority", ""))
            is_proj = self.dkind == "project"
            self.query_one("#d-why-box", Vertical).display = is_proj
            if is_proj:
                self.query_one("#d-why", Input).value = str(obj.get("goal", ""))
            crit_box = self.query_one("#d-crit", Vertical)
            crits = full.get("criteria", [])
            if not crits:
                crit_box.display = False
            for c in crits:
                self._crit_ids.append(int(c["id"]))
                crit_box.mount(
                    Checkbox(f"#{c['id']} {c['text']}", value=bool(c["done"]), id=f"crit-{c['id']}")
                )
            commits_box = self.query_one("#d-commits", Vertical)
            links = full.get("links", [])
            if not links:
                commits_box.display = False
            else:
                commits_box.mount(Static(render_commits(links), markup=False))

        def on_button_pressed(self, e: Button.Pressed) -> None:
            if e.button.id != "ok":
                self.dismiss(None)
                return
            store = self._dstore
            title = self.query_one("#d-title", Input).value
            desc = self.query_one("#d-desc", TextArea).text
            pri_raw = self.query_one("#d-pri", Input).value.strip()
            pri = pri_raw if pri_raw else ""
            try:
                for cid in self._crit_ids:
                    box = self.query_one(f"#crit-{cid}", Checkbox)
                    store.set_criteria(cid, box.value, actor="tui")
                if self.dkind == "project":
                    store.update_project(
                        self.doid,
                        name=title or None,
                        description=desc,
                        goal=self.query_one("#d-why", Input).value or None,
                        priority=pri,
                        actor="tui",
                    )
                elif self.dkind == "story":
                    store.update_story(
                        self.doid,
                        title=title or None,
                        description=desc,
                        priority=pri,
                        actor="tui",
                    )
                else:
                    store.update_task(
                        self.doid,
                        title=title or None,
                        description=desc,
                        priority=pri,
                        actor="tui",
                    )
            except ValueError as exc:
                self.notify(msg_error(exc))
                return
            self.dismiss(True)

    class HelpScreen(_Form):
        """Shared help text overlay; same source as `lpui help`."""

        HELP = HELP_TEXT

        def compose(self) -> ComposeResult:
            with Vertical(id="dlg"):
                yield Static(self.HELP, markup=False)
                yield Button("Close", id="cancel")

        def on_button_pressed(self, e: Button.Pressed) -> None:
            self.dismiss(None)
