"""TUI screens: modal forms and detail views.

The app shell (LazyplanApp) lives in tui.py; every overlay lives here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

try:
    from textual import on
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.events import DescendantBlur, DescendantFocus
    from textual.screen import ModalScreen, Screen
    from textual.widget import Widget
    from textual.widgets import (
        Button,
        Checkbox,
        Collapsible,
        Input,
        Label,
        OptionList,
        Static,
        TextArea,
    )

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from .design import HELP_TEXT, msg_error
from .render import render_commits

if TYPE_CHECKING:
    from .store import Store

from typing import cast

if _TEXTUAL_OK:

    def _row(*buttons: Button) -> Horizontal:
        """One compact action row (`.btn-row`): every editor and modal row."""
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
        """Create-plan form: title + priority + why + what."""

        def __init__(self, defaults: dict[str, str] | None = None) -> None:
            super().__init__()
            self._defaults = defaults or {}

        def compose(self) -> ComposeResult:
            with Vertical(id="dlg"):
                yield Label("New plan  (opens as P#...)")
                yield Input(placeholder="title *", id="f-title")
                yield Input(
                    value=self._defaults.get("priority", ""),
                    placeholder="priority p0..p3",
                    id="f-priority",
                )
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
                    for k in ("title", "priority", "why", "what")
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
                    value=self._defaults.get("priority", ""),
                    placeholder="priority p0..p3",
                    id="f-priority",
                )
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
                    for k in ("title", "priority", "desc")
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
                    value=self._defaults.get("priority", ""),
                    placeholder="priority p0..p3",
                    id="f-priority",
                )
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
                    for k in ("title", "priority", "desc")
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
            yield Input(placeholder="priority p0..p3 (empty clears)", id="d-pri")
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
            self.query_one("#d-pri", Input).value = str(obj.get("priority", ""))
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
            pri_raw = self.query_one("#d-pri", Input).value.strip()
            pri = pri_raw if pri_raw else ""
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
                        priority=pri,
                        actor="tui",
                    )
                elif self.dkind == "milestone":
                    store.update_milestone(
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
        """Fuzzy command palette: every tree action, keyboard-first."""

        COMMANDS: tuple[tuple[str, str], ...] = (
            ("new-context", "new context (n)"),
            ("new-plan", "new plan (P)"),
            ("new-milestone", "new milestone (M)"),
            ("new-task", "new task (T)"),
            ("editor", "project editor (e)"),
            ("export-md", "export plan .md (X)"),
            ("criteria", "tick criteria (c)"),
            ("delete", "delete with confirm (d)"),
            ("fold", "fold one (z)"),
            ("fold-all", "fold all (Z)"),
            ("filter", "status filter (f)"),
            ("show-all", "show all / capped (A)"),
            ("refresh", "refresh (r)"),
            ("help", "help (?)"),
            ("quit", "quit (q)"),
        )

        def compose(self) -> ComposeResult:
            with Vertical(id="dlg"):
                yield Label("palette — type to filter, enter to run, esc cancels")
                yield Input(placeholder="type a command…", id="palette-input")
                from textual.widgets.option_list import Option

                opts = [Option(label, id=cid) for cid, label in self.COMMANDS]
                yield OptionList(*opts, id="palette-list")

        def on_mount(self) -> None:
            try:
                self.query_one("#palette-input", Input).focus()
            except Exception:
                pass

        @on(Input.Changed, "#palette-input")
        def _filter(self, e: Input.Changed) -> None:
            query = e.value.strip().lower()
            try:
                from textual.widgets.option_list import Option

                lst = self.query_one("#palette-list", OptionList)
            except Exception:
                return
            lst.clear_options()
            for cid, label in self.COMMANDS:
                if not query or query in label.lower() or query in cid:
                    lst.add_option(Option(label, id=cid))
            e.stop()

        @on(Input.Submitted, "#palette-input")
        def _run_first(self, e: Input.Submitted) -> None:
            query = e.value.strip().lower()
            for cid, label in self.COMMANDS:
                if not query or query in label.lower() or query in cid:
                    self.dismiss(cid)
                    return
            self.dismiss(None)

        @on(OptionList.OptionSelected, "#palette-list")
        def _pick(self, e: OptionList.OptionSelected) -> None:
            opt_id = getattr(getattr(e, "option", None), "id", None)
            if opt_id:
                self.dismiss(str(opt_id))
            e.stop()

    class ProjectEditorScreen(Screen):
        """Fullscreen nested project editor: one plan, every card editable.

        Opened from any row; ``focus_kind``/``focus_id`` scroll to that
        card on mount. Per-row Save buttons plus a Save-all bar (ctrl+s);
        esc closes, prompting when dirty.
        """

        BINDINGS = [
            Binding("escape", "close", "Close", priority=True),
            Binding("ctrl+s", "save_all", "Save all", priority=True),
        ]

        def __init__(
            self,
            store: Store,
            plan_id: int,
            focus_kind: str | None = None,
            focus_id: int | None = None,
        ) -> None:
            super().__init__()
            self._estore = store
            self._plan_id = plan_id
            self._focus_kind = focus_kind or "plan"
            self._focus_id = focus_id if focus_id is not None else plan_id
            self._baseline: dict[str, object] = {}
            self._descs: dict[str, str] = {}
            self._desc_ids: set[str] = set()
            self._crit_owner: dict[int, tuple[str, int]] = {}
            self._ms_ids: list[int] = []
            self._task_ids: list[int] = []

        def compose(self) -> ComposeResult:
            yield Label(f"project editor — P#{self._plan_id} (ctrl+s saves all, esc closes)")
            with VerticalScroll(id="editor"):
                yield Vertical(id="cards")
            with Horizontal(id="editor-bar"):
                yield Button("Save", id="save-all", variant="primary")
                yield Button(".md", id="export-md")
                yield Button("+MS", id="add-ms")
                yield Button("Close", id="close")

        async def on_mount(self) -> None:
            await self._rebuild()
            self.call_after_refresh(self._scroll_to_anchor)

        def _scroll_to_anchor(self) -> None:
            """Focus the anchor card after layout so scrolling lands."""
            anchor = f"#anchor-{self._focus_kind}-{self._focus_id}"
            try:
                card = self.query_one(anchor, Collapsible)
            except Exception:
                card = None
            if card is not None:
                try:
                    self.query_one("#editor", VerticalScroll).scroll_to_widget(card, animate=False)
                except Exception:
                    pass
                try:
                    card.query_one("Input").focus()
                except Exception:
                    pass

        # -- card construction -----------------------------------------
        @staticmethod
        def _first_line(text: object) -> str:
            """One-line summary of a description."""
            lines = str(text or "").splitlines()
            return lines[0] if lines else ""

        def _sync_descs(self) -> None:
            """Fold widget edits back into the full-text map.

            Collapsed Inputs hold the first line only; the stored tail
            survives first-line edits. Expanded TextAreas hold full text.
            """
            for did in self._desc_ids:
                try:
                    try:
                        area = self.query_one(f"#{did}", TextArea)
                    except Exception:
                        area = None
                    if area is not None:
                        self._descs[did] = area.text
                        continue
                    inp = self.query_one(f"#{did}", Input)
                    tail = "\n".join(self._descs.get(did, "").splitlines()[1:])
                    self._descs[did] = inp.value + (f"\n{tail}" if tail else "")
                except Exception:
                    continue

        def _snapshot(self) -> None:
            """Baseline of every editable value; esc compares against this.

            Event-based dirty flags race mount-time Changed messages, so
            closeness to saved state is computed, never tracked.
            """
            self._sync_descs()
            base: dict[str, object] = {
                f"d:{did}": self._descs.get(did, "") for did in self._desc_ids
            }
            for inp in self.query(Input):
                if inp.id and inp.id not in self._desc_ids:
                    base[f"i:{inp.id}"] = inp.value
            for chk in self.query(Checkbox):
                if chk.id:
                    base[f"c:{chk.id}"] = chk.value
            self._baseline = base

        def _is_dirty(self) -> bool:
            """True when any editable value differs from the last save."""
            self._sync_descs()
            base = self._baseline
            for did in self._desc_ids:
                if base.get(f"d:{did}") != self._descs.get(did, ""):
                    return True
            for inp in self.query(Input):
                if inp.id and inp.id not in self._desc_ids and base.get(f"i:{inp.id}") != inp.value:
                    return True
            for chk in self.query(Checkbox):
                if chk.id and base.get(f"c:{chk.id}") != chk.value:
                    return True
            return False

        async def _expand_desc(self, did: str, first_line: str) -> None:
            """Swap a one-line description Input for a multi-line TextArea."""
            try:
                old = self.query_one(f"#{did}", Input)
            except Exception:
                return
            if old.parent is None:
                return
            parent = cast(Widget, old.parent)
            kids = list(parent.children)
            try:
                nxt = kids[kids.index(old) + 1]
            except (ValueError, IndexError):
                nxt = None
            tail = "\n".join(self._descs.get(did, "").splitlines()[1:])
            full = first_line + (f"\n{tail}" if tail else "")
            self._descs[did] = full
            area = TextArea(full, id=did)
            await old.remove()
            await parent.mount(area, before=nxt)
            area.focus()

        async def _collapse_desc(self, did: str, full: str) -> None:
            """Fold an expanded description back to one line."""
            try:
                old = self.query_one(f"#{did}", TextArea)
            except Exception:
                return
            if old.parent is None:
                return
            parent = cast(Widget, old.parent)
            kids = list(parent.children)
            try:
                nxt = kids[kids.index(old) + 1]
            except (ValueError, IndexError):
                nxt = None
            self._descs[did] = full
            await old.remove()
            await parent.mount(Input(value=self._first_line(full), id=did), before=nxt)

        @on(DescendantFocus)
        async def _expand_on_focus(self, e: DescendantFocus) -> None:
            """Descriptions edit multi-line while focused."""
            ctrl = getattr(e, "control", None)
            if isinstance(ctrl, Input) and ctrl.id in self._desc_ids:
                try:
                    self.query_one(f"#{ctrl.id}", TextArea)
                    return  # already expanded
                except Exception:
                    pass
                await self._expand_desc(ctrl.id, ctrl.value)

        @on(DescendantBlur)
        async def _collapse_on_blur(self, e: DescendantBlur) -> None:
            """Descriptions fold back to one line on blur."""
            ctrl = getattr(e, "control", None)
            if isinstance(ctrl, TextArea) and ctrl.id in self._desc_ids:
                await self._collapse_desc(ctrl.id, ctrl.text)

        def _crit_widgets(self, prefix: str, crits: list[dict]) -> list:
            """Checkbox rows plus header, for Collapsible constructors."""
            if not crits:
                return []
            out: list = [Label("acceptance (tick = done):")]
            for c in crits:
                cid = int(c["id"])
                out.append(
                    Checkbox(f"#{cid} {c['text']}", value=bool(c["done"]), id=f"{prefix}-{cid}")
                )
            return out

        async def _rebuild(self) -> None:
            from . import services as _services

            box = self.query_one("#cards", Vertical)
            await box.remove_children()
            self._crit_owner = {}
            self._ms_ids = []
            self._task_ids = []
            self._descs = {}
            self._desc_ids = set()
            full = self._estore.get_full("plan", self._plan_id)
            if full is None:
                await box.mount(Label("plan no longer exists — esc to close"))
                return
            focus_ms: int | None = None
            if self._focus_kind == "task":
                trow = self._estore.get_task(self._focus_id)
                focus_ms = trow.milestone_id if trow else None
            elif self._focus_kind == "milestone":
                focus_ms = self._focus_id
            p = full["plan"]
            self._descs["p-desc"] = str(p.get("description", ""))
            self._desc_ids.add("p-desc")
            for c in full.get("criteria", []):
                self._crit_owner[int(c["id"])] = ("plan", int(p["id"]))
            plan_card = Collapsible(
                Input(value=str(p.get("name", "")), id="p-title"),
                Input(value=self._first_line(p.get("description", "")), id="p-desc"),
                Input(value=str(p.get("goal", "")), placeholder="why", id="p-why"),
                Input(
                    value=str(p.get("priority", "")),
                    placeholder="priority p0..p3 (empty clears)",
                    id="p-pri",
                ),
                *self._crit_widgets("pcrit", full.get("criteria", [])),
                _row(
                    Button("Save", id="save-plan"),
                    Button(f"{p.get('status', '')}", id="status-plan"),
                ),
                title=f"P#{p['id']} {p.get('name', '')} [{p.get('status', '')}]",
                collapsed=self._focus_kind != "plan",
                id="anchor-plan-{}".format(p["id"]),
            )
            await box.mount(plan_card)
            for entry in full.get("milestones", []):
                s = entry["milestone"]
                sid = int(s["id"])
                self._ms_ids.append(sid)
                did = f"s-{sid}-desc"
                self._descs[did] = str(s.get("description", ""))
                self._desc_ids.add(did)
                for c in entry.get("criteria", []):
                    self._crit_owner[int(c["id"])] = ("milestone", sid)
                card = Collapsible(
                    Input(value=str(s.get("title", "")), id=f"s-{sid}-title"),
                    Input(value=self._first_line(s.get("description", "")), id=did),
                    Input(
                        value=str(s.get("priority", "")),
                        placeholder="priority p0..p3 (empty clears)",
                        id=f"s-{sid}-pri",
                    ),
                    *self._crit_widgets(f"scrit-{sid}", entry.get("criteria", [])),
                    _row(
                        Button("Save", id=f"save-ms-{sid}"),
                        Button(f"{s.get('status', '')}", id=f"status-ms-{sid}"),
                        Button("+Task", id=f"add-task-{sid}"),
                        Button("Del", id=f"del-ms-{sid}", variant="error"),
                    ),
                    title=f"M#{sid} {s.get('title', '')} [{s.get('status', '')}]",
                    collapsed=sid != focus_ms,
                    id=f"anchor-milestone-{sid}",
                )
                await box.mount(card)
                for t in entry.get("tasks", []):
                    tid = int(t["id"])
                    self._task_ids.append(tid)
                    tdid = f"t-{tid}-desc"
                    self._descs[tdid] = str(t.get("description", ""))
                    self._desc_ids.add(tdid)
                    tcrits = [c for c in self._estore.list_criteria("task", tid)]
                    for c in tcrits:
                        self._crit_owner[int(c.id)] = ("task", tid)
                    tcard = Collapsible(
                        Input(value=str(t.get("title", "")), id=f"t-{tid}-title"),
                        Input(value=self._first_line(t.get("description", "")), id=tdid),
                        Input(
                            value=str(t.get("priority", "")),
                            placeholder="priority p0..p3 (empty clears)",
                            id=f"t-{tid}-pri",
                        ),
                        *self._crit_widgets(
                            f"tcrit-{tid}",
                            [{"id": c.id, "text": c.text, "done": c.done} for c in tcrits],
                        ),
                        _row(
                            Button("Save", id=f"save-task-{tid}"),
                            Button(f"{t.get('status', '')}", id=f"status-task-{tid}"),
                            Button("Del", id=f"del-task-{tid}", variant="error"),
                        ),
                        title=f"T#{tid} {t.get('title', '')} [{t.get('status', '')}]",
                        collapsed=not (self._focus_kind == "task" and self._focus_id == tid),
                        id=f"anchor-task-{tid}",
                    )
                    await box.mount(tcard)
            _ = _services  # kept for structural-action parity with tui.py
            self._snapshot()

        # -- writes ------------------------------------------------------
        def _save_plan(self) -> None:
            self._sync_descs()
            title = self.query_one("#p-title", Input).value
            desc = self._descs.get("p-desc", "")
            why = self.query_one("#p-why", Input).value
            pri_raw = self.query_one("#p-pri", Input).value.strip()
            for cid, (kind, _) in list(self._crit_owner.items()):
                if kind != "plan":
                    continue
                try:
                    box = self.query_one(f"#pcrit-{cid}", Checkbox)
                except Exception:
                    continue
                self._estore.set_criteria(cid, box.value, actor="tui")
            self._estore.update_plan(
                self._plan_id,
                name=title or None,
                description=desc,
                goal=why or None,
                priority=pri_raw if pri_raw else "",
                actor="tui",
            )

        def _save_milestone(self, sid: int) -> None:
            self._sync_descs()
            title = self.query_one(f"#s-{sid}-title", Input).value
            desc = self._descs.get(f"s-{sid}-desc", "")
            pri_raw = self.query_one(f"#s-{sid}-pri", Input).value.strip()
            for cid, (kind, oid) in list(self._crit_owner.items()):
                if kind != "milestone" or oid != sid:
                    continue
                try:
                    box = self.query_one(f"#scrit-{sid}-{cid}", Checkbox)
                except Exception:
                    continue
                self._estore.set_criteria(cid, box.value, actor="tui")
            self._estore.update_milestone(
                sid,
                title=title or None,
                description=desc,
                priority=pri_raw if pri_raw else "",
                actor="tui",
            )

        def _save_task(self, tid: int) -> None:
            self._sync_descs()
            title = self.query_one(f"#t-{tid}-title", Input).value
            desc = self._descs.get(f"t-{tid}-desc", "")
            pri_raw = self.query_one(f"#t-{tid}-pri", Input).value.strip()
            for cid, (kind, oid) in list(self._crit_owner.items()):
                if kind != "task" or oid != tid:
                    continue
                try:
                    box = self.query_one(f"#tcrit-{tid}-{cid}", Checkbox)
                except Exception:
                    continue
                self._estore.set_criteria(cid, box.value, actor="tui")
            self._estore.update_task(
                tid,
                title=title or None,
                description=desc,
                priority=pri_raw if pri_raw else "",
                actor="tui",
            )

        def _save_all(self) -> None:
            self._save_plan()
            for sid in list(self._ms_ids):
                self._save_milestone(sid)
            for tid in list(self._task_ids):
                self._save_task(tid)
            self._snapshot()

        def action_save_all(self) -> None:
            try:
                self._save_all()
            except ValueError as exc:
                self.notify(msg_error(exc))
                return
            try:
                from .messages import RowAction

                self.post_message(RowAction("editor-saved", "plan", self._plan_id))
            except Exception:
                pass
            self.notify("saved all cards")

        def action_close(self) -> None:
            if not self._is_dirty():
                self.dismiss(None)
                return

            def cb(confirmed: bool | None) -> None:
                if confirmed:
                    self.dismiss(None)

            self.app.push_screen(ConfirmScreen("Discard unsaved changes?"), cb)

        @on(Button.Pressed, "#save-all")
        def _press_save_all(self) -> None:
            self.action_save_all()

        def _announce_editor_saved(self) -> None:
            try:
                from .messages import RowAction

                self.post_message(RowAction("editor-saved", "plan", self._plan_id))
            except Exception:
                pass

        @on(Button.Pressed, "#save-plan")
        def _press_save_plan(self) -> None:
            try:
                self._save_plan()
                self._snapshot()
                self._announce_editor_saved()
                self.notify("plan saved")
            except ValueError as exc:
                self.notify(msg_error(exc))

        @on(Button.Pressed, "#close")
        def _press_close(self) -> None:
            self.action_close()

        @on(Button.Pressed, "#export-md")
        def _press_export(self) -> None:
            from . import services as _services

            try:
                entry = _services.export_plan(self._estore, self._plan_id)
                if entry is None:
                    self.notify("plan no longer exists")
                    return
                from .render import render_plan_markdown

                path = f"plan-P{self._plan_id}.md"
                with open(path, "w") as fh:
                    fh.write(render_plan_markdown(entry) + "\n")
                self.notify(f"exported {path}")
            except ValueError as exc:
                self.notify(msg_error(exc))

        @on(Button.Pressed, "#add-ms")
        def _press_add_ms(self) -> None:
            self._add_milestone()

        @on(Button.Pressed, ".btn-row Button")
        async def _press_card_button(self, e: Button.Pressed) -> None:
            """Card actions dispatched by id prefix (dynamic save/status/del)."""
            from . import services as _services

            bid = e.button.id or ""
            if bid in ("save-all", "save-plan", "close", "export-md", "add-ms"):
                return  # handled by specific @on handlers above
            try:
                if bid.startswith("save-ms-"):
                    self._save_milestone(int(bid[len("save-ms-") :]))
                    self._snapshot()
                    self.notify("milestone saved")
                elif bid.startswith("save-task-"):
                    self._save_task(int(bid[len("save-task-") :]))
                    self._snapshot()
                    self.notify("task saved")
                elif bid.startswith("add-task-"):
                    self._add_task(int(bid[len("add-task-") :]))
                elif bid.startswith("status-plan"):
                    _services.cycle_status(self._estore, "plan", self._plan_id, actor="tui")
                    self._snapshot()
                    await self._rebuild()
                elif bid.startswith("status-ms-"):
                    _services.cycle_status(
                        self._estore, "milestone", int(bid[len("status-ms-") :]), actor="tui"
                    )
                    self._snapshot()
                    await self._rebuild()
                elif bid.startswith("status-task-"):
                    _services.cycle_status(
                        self._estore, "task", int(bid[len("status-task-") :]), actor="tui"
                    )
                    self._snapshot()
                    await self._rebuild()
                elif bid.startswith("del-ms-"):
                    self._confirm_delete("milestone", int(bid[len("del-ms-") :]))
                elif bid.startswith("del-task-"):
                    self._confirm_delete("task", int(bid[len("del-task-") :]))
            except ValueError as exc:
                self.notify(msg_error(exc))
            e.stop()

        def _add_milestone(self) -> None:
            def cb(data: dict | None) -> None:
                if not data:
                    return
                from . import services as _services

                try:
                    _services.create_milestone(
                        self._estore,
                        self._plan_id,
                        data["title"],
                        data["desc"],
                        priority=data["priority"],
                        actor="tui",
                    )
                except (ValueError, KeyError) as exc:
                    self.notify(msg_error(exc))
                    return
                self._snapshot()
                self.run_worker(self._rebuild())

            self.app.push_screen(NewMilestoneScreen(self._plan_id), cb)

        def _add_task(self, sid: int) -> None:
            def cb(data: dict | None) -> None:
                if not data:
                    return
                from . import services as _services

                try:
                    _services.create_task(
                        self._estore,
                        sid,
                        data["title"],
                        data["desc"],
                        priority=data["priority"],
                        actor="tui",
                    )
                except (ValueError, KeyError) as exc:
                    self.notify(msg_error(exc))
                    return
                self._snapshot()
                self.run_worker(self._rebuild())

            self.app.push_screen(NewTaskScreen(sid), cb)

        def _confirm_delete(self, kind: str, oid: int) -> None:
            def cb(confirmed: bool | None) -> None:
                if not confirmed:
                    return
                if not self._estore.delete(kind, oid, actor="tui"):
                    self.notify("already gone")
                    return
                self._snapshot()
                self.run_worker(self._rebuild())

            self.app.push_screen(ConfirmScreen(f"Delete {kind} #{oid}?\n(children go too.)"), cb)
