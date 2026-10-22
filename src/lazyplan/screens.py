"""TUI screens: modal forms and detail views.

The app shell (LazyplanApp) lives in tui.py; every overlay lives here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

try:
    from textual import on
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical
    from textual.screen import ModalScreen
    from textual.widgets import (
        Button,
        Checkbox,
        Input,
        Label,
        OptionList,
        Static,
        TextArea,
    )
    from textual.widgets.option_list import Option

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from .design import HELP_TEXT, PALETTE_COMMANDS, PALETTE_SECTIONS, msg_error
from .render import render_commits

if TYPE_CHECKING:
    from .store import Store

if _TEXTUAL_OK:

    def _row(*buttons: Button) -> Horizontal:
        """One compact action row (`.btn-row`): every modal row."""
        return Horizontal(*buttons, classes="btn-row")

    class _Form(ModalScreen):
        """Modal base; dialog chrome comes from design.APP_CSS.

        Esc backs out of every form without saving (matches the Cancel
        button); per-screen callbacks already treat a None result as cancel.
        """

        BINDINGS = [Binding("escape", "cancel", "Cancel")]

        def action_cancel(self) -> None:
            """Return to the previous screen, discarding edits."""
            self.dismiss(None)

    class NewPlanScreen(_Form):
        """Create-plan form: title + why + what."""

        def __init__(self, defaults: dict[str, str] | None = None) -> None:
            super().__init__()
            self._defaults = defaults or {}

        def compose(self) -> ComposeResult:
            with Vertical(id="dlg"):
                yield Label("New plan  (opens as P#...)")
                yield Input(placeholder="title *", id="f-title")
                yield Input(
                    value=self._defaults.get("why", ""),
                    placeholder="why does this exist?",
                    id="f-why",
                )
                yield Input(
                    value=self._defaults.get("what", ""),
                    placeholder="what gets built?",
                    id="f-what",
                )
                with _row():
                    yield Button("Create", id="ok")
                    yield Button("Cancel", id="cancel")

        @on(Button.Pressed, "#ok")
        def _create(self) -> None:
            self.dismiss(
                {
                    k: self.query_one(f"#f-{k}", Input).value.strip()
                    for k in ("title", "why", "what")
                }
            )

        @on(Button.Pressed, "#cancel")
        def _cancel(self) -> None:
            self.dismiss(None)

    class NewMilestoneScreen(_Form):
        """Create-milestone form for one plan."""

        def __init__(self, plan_id: int, defaults: dict[str, str] | None = None) -> None:
            super().__init__()
            self.plan_id = plan_id
            self._defaults = defaults or {}

        def compose(self) -> ComposeResult:
            with Vertical(id="dlg"):
                yield Label(f"New milestone in P#{self.plan_id}")
                yield Input(placeholder="title *", id="f-title")
                yield Input(
                    value=self._defaults.get("desc", ""),
                    placeholder="details",
                    id="f-desc",
                )
                with _row():
                    yield Button("Create", id="ok")
                    yield Button("Cancel", id="cancel")

        @on(Button.Pressed, "#ok")
        def _create(self) -> None:
            self.dismiss(
                {
                    k: self.query_one(f"#f-{k}", Input).value.strip()
                    for k in ("title", "desc")
                }
            )

        @on(Button.Pressed, "#cancel")
        def _cancel(self) -> None:
            self.dismiss(None)

    class NewTaskScreen(_Form):
        """Create-task form for one milestone."""

        def __init__(self, milestone_id: int, defaults: dict[str, str] | None = None) -> None:
            super().__init__()
            self.milestone_id = milestone_id
            self._defaults = defaults or {}

        def compose(self) -> ComposeResult:
            with Vertical(id="dlg"):
                yield Label(f"New task in M#{self.milestone_id}")
                yield Input(placeholder="title *", id="f-title")
                yield Input(
                    value=self._defaults.get("desc", ""),
                    placeholder="details",
                    id="f-desc",
                )
                with _row():
                    yield Button("Create", id="ok")
                    yield Button("Cancel", id="cancel")

        @on(Button.Pressed, "#ok")
        def _create(self) -> None:
            self.dismiss(
                {
                    k: self.query_one(f"#f-{k}", Input).value.strip()
                    for k in ("title", "desc")
                }
            )

        @on(Button.Pressed, "#cancel")
        def _cancel(self) -> None:
            self.dismiss(None)

    class ConfirmScreen(_Form):
        """Delete confirmation; dismisses True on Delete."""

        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

        def compose(self) -> ComposeResult:
            with Vertical(id="dlg"):
                yield Static(self.text, markup=False)
                with _row():
                    yield Button("Delete", id="ok", variant="error")
                    yield Button("Cancel", id="cancel")

        @on(Button.Pressed, "#ok")
        def _confirm(self) -> None:
            self.dismiss(True)

        @on(Button.Pressed, "#cancel")
        def _cancel(self) -> None:
            self.dismiss(False)

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
            with Vertical(id="d-why-box"):
                yield Input(placeholder="why does this exist?", id="d-why")
            with Vertical(id="d-crit"):
                yield Label("acceptance (tick = done):")
            with Vertical(id="d-commits"):
                yield Label("commits:")
            with Vertical(id="d-repos"):
                yield Label("repos:")
            with _row():
                yield Button("Save", id="ok", variant="primary")
                yield Button("Cancel", id="cancel")

        def on_mount(self) -> None:
            full = self._dstore.get_full(self.dkind, self.doid)
            if full is None:
                self.dismiss(None)
                return
            obj = full[{"plan": "plan", "milestone": "milestone", "task": "task"}[self.dkind]]
            self.query_one("#d-title", Input).value = str(obj.get("title", obj.get("name", "")))
            self.query_one("#d-desc", TextArea).text = str(obj.get("description", ""))
            is_proj = self.dkind == "plan"
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
            repos_box = self.query_one("#d-repos", Vertical)
            repos = full.get("effective_repos") or full.get("repos") or []
            if not repos:
                repos_box.display = False
            else:
                lines = [
                    str(r.get("repo_path", ""))
                    + (f" ({r.get('repo_remote')})" if r.get("repo_remote") else "")
                    for r in repos
                ]
                repos_box.mount(Static("\n".join(lines), markup=False))
            try:
                self.query_one("#d-title", Input).focus()
            except Exception:
                pass

        @on(Button.Pressed, "#ok")
        def _save(self) -> None:
            store = self._dstore
            title = self.query_one("#d-title", Input).value
            desc = self.query_one("#d-desc", TextArea).text
            try:
                for cid in self._crit_ids:
                    box = self.query_one(f"#crit-{cid}", Checkbox)
                    store.set_criteria(cid, box.value, actor="tui")
                if self.dkind == "plan":
                    store.update_plan(
                        self.doid,
                        name=title or None,
                        description=desc,
                        goal=self.query_one("#d-why", Input).value or None,
                        actor="tui",
                    )
                elif self.dkind == "milestone":
                    store.update_milestone(
                        self.doid,
                        title=title or None,
                        description=desc,
                        actor="tui",
                    )
                else:
                    store.update_task(
                        self.doid,
                        title=title or None,
                        description=desc,
                        actor="tui",
                    )
            except ValueError as exc:
                self.notify(msg_error(exc))
                return
            try:
                from .messages import RowAction

                self.post_message(RowAction("detail-saved", self.dkind, self.doid))
            except Exception:
                pass
            self.dismiss(True)

        @on(Button.Pressed, "#cancel")
        def _cancel(self) -> None:
            self.dismiss(None)

    class HelpScreen(_Form):
        """Shared help text overlay; same source as `lpui help`."""

        HELP = HELP_TEXT

        def compose(self) -> ComposeResult:
            with Vertical(id="dlg"):
                yield Static(self.HELP, markup=False)
                yield Button("Close", id="cancel")

        @on(Button.Pressed, "#cancel")
        def _close(self) -> None:
            self.dismiss(None)

    class PaletteScreen(_Form):
        """Modal command palette: grouped sections, live-filtered, one keypress away."""

        COMMANDS = PALETTE_COMMANDS
        SECTIONS = PALETTE_SECTIONS

        @staticmethod
        def _matching(query: str) -> list[tuple[str, list[tuple[str, str]]]]:
            """Non-empty sections for a query; headers never match."""
            q = query.strip().lower()
            out: list[tuple[str, list[tuple[str, str]]]] = []
            for header, ids in PaletteScreen.SECTIONS:
                cmds = [
                    (cid, label)
                    for cid, label in PaletteScreen.COMMANDS
                    if cid in ids and (not q or q in label.lower() or q in cid)
                ]
                if cmds:
                    out.append((header, cmds))
            return out

        @staticmethod
        def _section_options(
            sections: list[tuple[str, list[tuple[str, str]]]],
        ) -> list:
            opts: list = []
            for header, cmds in sections:
                opts.append(Option(f"── {header} ──", disabled=True))
                opts.extend(Option(label, id=cid) for cid, label in cmds)
            return opts

        def compose(self) -> ComposeResult:
            with Vertical(id="dlg"):
                yield Label("palette — type to filter, enter to run, esc cancels")
                yield Input(placeholder="type a command…", id="palette-input")
                yield OptionList(*self._section_options(self._matching("")), id="palette-list")

        def on_mount(self) -> None:
            try:
                self.query_one("#palette-input", Input).focus()
            except Exception:
                pass

        @on(Input.Changed, "#palette-input")
        def _filter(self, e: Input.Changed) -> None:
            try:
                lst = self.query_one("#palette-list", OptionList)
            except Exception:
                return
            lst.clear_options()
            for opt in self._section_options(self._matching(e.value)):
                lst.add_option(opt)
            e.stop()

        @on(Input.Submitted, "#palette-input")
        def _run_first(self, e: Input.Submitted) -> None:
            for _, cmds in self._matching(e.value):
                if cmds:
                    self.dismiss(cmds[0][0])
                    return
            self.dismiss(None)

        @on(OptionList.OptionSelected, "#palette-list")
        def _pick(self, e: OptionList.OptionSelected) -> None:
            opt_id = getattr(getattr(e, "option", None), "id", None)
            if opt_id:
                self.dismiss(str(opt_id))
            e.stop()

    class FilterPromptScreen(_Form):
        """Prompt for tree filter text; empty clears the filter."""

        def compose(self) -> ComposeResult:
            with Vertical(id="dlg"):
                yield Label("filter tree by text (empty clears)")
                yield Input(placeholder="filter text…", id="filter-input")
                with _row():
                    yield Button("Apply", id="ok", variant="primary")
                    yield Button("Cancel", id="cancel")

        def on_mount(self) -> None:
            try:
                self.query_one("#filter-input", Input).focus()
            except Exception:
                pass

        @on(Button.Pressed, "#ok")
        def _apply(self) -> None:
            self.dismiss(self.query_one("#filter-input", Input).value.strip())

        @on(Button.Pressed, "#cancel")
        def _cancel(self) -> None:
            self.dismiss(None)

        @on(Input.Submitted, "#filter-input")
        def _submit(self) -> None:
            self.dismiss(self.query_one("#filter-input", Input).value.strip())

