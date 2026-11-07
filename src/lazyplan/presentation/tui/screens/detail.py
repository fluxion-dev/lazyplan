"""TUI screens: modal forms and detail views.

The app shell (LazyplanApp) lives in tui.py; every overlay lives here.
"""

from __future__ import annotations

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

from lazyplan.infrastructure.templates import load_template
from lazyplan.services.source import SourceTrail, build_source_trail

from .... import services
from ...shared.design import msg_error
from ..views.detail import build_detail, detail_breadcrumb

if TYPE_CHECKING:
    from ....core.ports.provenance import ProvenancePort
from .base import _row
from .detail_questions import QuestionActionsMixin
from .forms import ConfirmScreen, FilterPromptScreen, NewMilestoneScreen, NewTaskScreen

if _TEXTUAL_OK:

    class DetailScreen(QuestionActionsMixin, Screen):
        """Read-first detail page; `e` switches to an in-place edit form."""

        BINDINGS = [
            Binding("escape", "back", "Back", priority=True),
            Binding("e", "toggle_edit", "Edit"),
            Binding("s", "advance_status", "Status"),
            Binding("x", "tick_criterion", "Tick"),
            Binding("a", "add_criterion", "Criterion"),
            Binding("p", "prove_criterion", "Prove"),
            Binding("q", "add_question", "Question"),
            Binding("Q", "resolve_question", "Resolve"),
            Binding("R", "reopen_question", "Reopen"),
            Binding("n", "add_child", "New child"),
            Binding("d", "delete_row", "Delete"),
            Binding("g", "open_source", "Source"),
            Binding("ctrl+s", "save", "Save", priority=True),
        ]

        def __init__(self, store: ProvenancePort, kind: str, oid: int, edit: bool = False) -> None:
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
                    yield Label("Edit details", classes="form-title")
                    yield Label("Title [dim](required)[/]", classes="field-label")
                    yield Input(placeholder="title", id="d-title")
                    if self.dkind == "plan":
                        yield Label("Why", classes="field-label")
                        yield Input(placeholder="why does this exist?", id="d-why")
                        yield Label("What", classes="field-label")
                    else:
                        yield Label("Details", classes="field-label")
                    yield TextArea(id="d-desc")
                    with _row():
                        yield Button("Save", id="ok", variant="primary")
                        yield Button("Cancel", id="cancel")
                yield Label("", id="detail-hints")

        def on_mount(self) -> None:
            page = self.query_one("#detail-page")
            page.border_title = " detail "
            width = self.app.size.width
            self.set_class(width < 80, "compact")
            self.set_class(width >= 120, "wide")
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
            return detail_breadcrumb(self._dstore, self.dkind, self.doid, self._obj())

        def _render_read(self) -> None:
            document = build_detail(
                self._dstore,
                self.dkind,
                self.doid,
                self._full,
                self._trail,
            )
            self.query_one("#detail-head", Static).update(document.head)
            self.query_one("#detail-body", Static).update(document.body)

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

        def _require_override(self) -> bool:
            """Writes are blocked until manual override mode is on."""
            gate = getattr(self.app, "require_override", None)
            if callable(gate):
                return bool(gate())
            return bool(getattr(self.app, "override_mode", False))

        def _record(self, action: str, reason: str = "") -> None:
            """Record one audited override for this detail write."""
            record = getattr(self.app, "_record_override", None)
            if callable(record):
                record(action, f"{self.dkind} #{self.doid}", reason)

        def action_toggle_edit(self) -> None:
            if not self._editing and not self._require_override():
                return
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
            if not self._require_override():
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
            self._record("edit")
            from ...shared.messages import RowAction  # noqa: F401

            self.post_message(RowAction("detail-saved", self.dkind, self.doid))
            self._reload()
            self.notify("saved")

        def action_advance_status(self) -> None:
            if self._editing:
                self.notify("save or cancel first")
                return
            if not self._require_override():
                return
            nxt = services.cycle_status(self._dstore, self.dkind, self.doid, actor="tui")
            self._record("status", nxt.value if nxt is not None else "")
            self._reload()
            if nxt is not None:
                self.notify(f"{self.dkind} {self.doid} -> {nxt.value}")

        def action_tick_criterion(self) -> None:
            if self._editing:
                self.notify("save or cancel first")
                return
            if not self._require_override():
                return
            items = self._dstore.list_criteria(self.dkind, self.doid)
            open_items = [c for c in items if not c.done]
            if not open_items:
                self.notify("no open criteria")
                return
            target = open_items[0]
            self._dstore.set_criteria(target.id, True, actor="tui")
            self._record("criterion tick", f"C{target.id}")
            self._reload()
            self.notify(f"criterion {target.id} checked")

        def action_prove_criterion(self) -> None:
            if self._editing:
                self.notify("save or cancel first")
                return
            if not self._require_override():
                return
            from .prove import prove_dialog

            def done(criterion_id: int, result: services.ProofResult) -> None:
                evidence = getattr(result, "evidence", None)
                detail = getattr(evidence, "command", "") or getattr(evidence, "note", "")
                self._record("criterion prove", str(detail))
                self._reload()
                self.notify(f"criterion {criterion_id} recorded", timeout=4)

            prove_dialog(self, self._dstore, self.dkind, self.doid, done)

        def action_add_criterion(self) -> None:
            if self._editing:
                self.notify("save or cancel first")
                return
            if not self._require_override():
                return

            def cb(text: str | None) -> None:
                if not text:
                    return
                criterion = self._dstore.add_criteria(self.dkind, self.doid, text, actor="tui")
                self._record("criterion add", f"C{criterion.id}")
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
            if not self._require_override():
                return
            if self.dkind == "plan":
                plan_id = self.doid

                def add_milestone(data: dict | None) -> None:
                    if not data:
                        return
                    created = services.create_milestone(
                        self._dstore,
                        plan_id,
                        data["title"],
                        data["desc"],
                        actor="tui",
                    )
                    self._record("milestone add", f"M{created.id}")
                    self._reload()

                self.app.push_screen(
                    NewMilestoneScreen(
                        plan_id,
                        defaults=load_template("milestone", self._dstore.db_path).defaults,
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
                    created = services.create_task(
                        self._dstore,
                        milestone_id,
                        data["title"],
                        data["desc"],
                        actor="tui",
                    )
                    self._record("task add", f"T{created.id}")
                    self._reload()

                self.app.push_screen(
                    NewTaskScreen(
                        milestone_id,
                        defaults=load_template("task", self._dstore.db_path).defaults,
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
            if not self._require_override():
                return
            from .detail_delete import confirm_delete

            confirm_delete(self)
