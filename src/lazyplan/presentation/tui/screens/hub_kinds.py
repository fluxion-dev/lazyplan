"""Trust hub kinds: criteria, evidence, questions, and references."""

from __future__ import annotations

import webbrowser
from typing import Any

from .... import services
from ....core.policies.evidence import proof_state
from ...shared.design import escape_markup
from .forms import ConfirmScreen, FilterPromptScreen
from .prove import prove_dialog

try:
    from textual.binding import Binding

    from .hub import HubEntry, HubScreen

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover - stdlib-only interpreter
    _TEXTUAL_OK = False


if _TEXTUAL_OK:

    class CriteriaHub(HubScreen):
        """Criteria of one plan, milestone, or task, with evidence state."""

        kind = "criteria"
        BINDINGS = [Binding("e", "edit_row", "Edit")]

        def __init__(self, store: Any, parent_kind: str, parent_id: int) -> None:
            super().__init__(store)
            self.parent_kind = parent_kind
            self.parent_id = parent_id
            self.title = f"criteria · {parent_kind} #{parent_id}"
            self.empty = "No criteria yet. Press a to add one."

        @property
        def source_parent(self) -> tuple[str, int] | None:
            return (self.parent_kind, self.parent_id)

        def load_entries(self) -> list[HubEntry]:
            out: list[HubEntry] = []
            for criterion in self.store.list_criteria(self.parent_kind, self.parent_id):
                evidence = services.list_evidence(self.store, criterion.id)
                state = proof_state(evidence)
                mark = "x" if criterion.done else " "
                body = (
                    f"C{criterion.id} · {'done' if criterion.done else 'open'}\n"
                    f"{escape_markup(criterion.text)}\n\n"
                    f"evidence {len(evidence)} · latest {state}"
                )
                tasks = self.store.criterion_tasks(criterion.id)
                if tasks:
                    body += "\nproving tasks " + ", ".join(f"T{task.id}" for task in tasks)
                out.append(
                    HubEntry(criterion.id, f"[{mark}] C{criterion.id} {criterion.text}", body)
                )
            return out

        def add(self) -> None:
            def cb(text: str | None) -> None:
                if not text:
                    return
                self.store.add_criteria(self.parent_kind, self.parent_id, text, actor="tui")
                self._reload()

            self.app.push_screen(
                FilterPromptScreen("New criterion", "what must be true?", "Add"), cb
            )

        def toggle(self) -> None:
            entry = self._selected()
            if entry is None:
                self._notify_empty()
                return
            criterion = self.store.get_criterion(entry.oid)
            if criterion is None:
                return
            self.store.set_criteria(criterion.id, not criterion.done, actor="tui")
            self._reload()

        def prove(self) -> None:
            entry = self._selected()
            if entry is None:
                self._notify_empty()
                return

            def done(_cid: int, _result: services.ProofResult) -> None:
                self._reload()

            prove_dialog(
                self,
                self.store,
                self.parent_kind,
                self.parent_id,
                done,
                criterion_id=entry.oid,
            )

        def edit_row(self) -> None:
            entry = self._selected()
            if entry is None:
                self._notify_empty()
                return
            criterion = self.store.get_criterion(entry.oid)
            if criterion is None:
                return

            def cb(text: str | None) -> None:
                if not text:
                    return
                try:
                    self.store.update_criterion(
                        criterion.id, text, actor="tui", reason="edited from hub"
                    )
                except ValueError as exc:
                    self.notify(f"error: {exc}", timeout=4)
                    return
                self._reload()

            self.app.push_screen(
                FilterPromptScreen(
                    "Edit criterion", "criterion text", "Save", initial=criterion.text
                )
            )

        def action_edit_row(self) -> None:
            self.edit_row()

        def delete_row(self) -> None:
            entry = self._selected()
            if entry is None:
                self._notify_empty()
                return

            def cb(confirmed: bool | None) -> None:
                if confirmed:
                    self.store.delete_criteria(entry.oid, actor="tui", reason="deleted from hub")
                    self._reload()

            self.app.push_screen(ConfirmScreen(f"Delete criterion C{entry.oid}?"), cb)

        def _task_id(self, action: str) -> None:
            entry = self._selected()
            if entry is None:
                self._notify_empty()
                return

            def cb(text: str | None) -> None:
                if not text:
                    return
                try:
                    task_id = int(text)
                    if action == "relate":
                        self.store.relate_criterion(entry.oid, task_id, actor="tui")
                    else:
                        self.store.unrelate_criterion(entry.oid, task_id, actor="tui")
                except (ValueError, KeyError) as exc:
                    self.notify(f"error: {exc}", timeout=4)
                    return
                self._reload()

            self.app.push_screen(FilterPromptScreen("Proving task", "task id", action.title()), cb)

        def relate(self) -> None:
            self._task_id("relate")

        def unrelate(self) -> None:
            self._task_id("unrelate")

        def open_entry(self, entry: HubEntry) -> None:
            self.app.push_screen(EvidenceHub(self.store, entry.oid, context=self.title))

    class EvidenceHub(HubScreen):
        """Evidence rows for one criterion, with prove and open actions."""

        kind = "evidence"

        def __init__(self, store: Any, criterion_id: int, context: str = "") -> None:
            super().__init__(store)
            self.criterion_id = criterion_id
            self.title = f"evidence · C{criterion_id}" + (f" · {context}" if context else "")
            self.empty = "No evidence yet. Press p to record proof."
            self._rows: dict[int, Any] = {}

        @property
        def source_parent(self) -> tuple[str, int] | None:
            criterion = self.store.get_criterion(self.criterion_id)
            if criterion is None:
                return None
            return (criterion.parent_kind, criterion.parent_id)

        def load_entries(self) -> list[HubEntry]:
            out: list[HubEntry] = []
            self._rows = {}
            for row in services.list_evidence(self.store, self.criterion_id):
                self._rows[row.id] = row
                state = proof_state([row])
                command = row.command or row.note or "(no command)"
                body = (
                    f"E{row.id} · {state}\n"
                    f"command  {escape_markup(command)}\n"
                    f"exit     {row.exit_code if row.exit_code is not None else '—'}\n"
                    f"commit   {escape_markup(row.commit_sha or '—')}\n"
                    f"task     {f'T{row.task_id}' if row.task_id else '—'}\n"
                    f"note     {escape_markup(row.note or '—')}"
                )
                out.append(HubEntry(row.id, f"E{row.id} {state} {command[:44]}", body))
            return out

        def prove(self) -> None:
            criterion = self.store.get_criterion(self.criterion_id)
            if criterion is None:
                return

            def done(_cid: int, _result: services.ProofResult) -> None:
                self._reload()

            prove_dialog(
                self,
                self.store,
                criterion.parent_kind,
                criterion.parent_id,
                done,
                criterion_id=self.criterion_id,
            )

        def open_value(self) -> None:
            entry = self._selected()
            row = self._rows.get(entry.oid) if entry is not None else None
            if row is None:
                self._notify_empty()
                return
            if row.pr_url:
                webbrowser.open(row.pr_url)
                self.notify(f"opened {row.pr_url}", timeout=4)
            elif row.commit_sha:
                self.app.copy_to_clipboard(row.commit_sha)
                self.notify(f"copied {row.commit_sha}", timeout=3)
            else:
                self.notify("no commit or pull request to open", timeout=3)

        def open_entry(self, entry: HubEntry) -> None:
            self.open_value()

    class QuestionsHub(HubScreen):
        """Open and resolved questions on one plan, with readiness impact."""

        kind = "questions"

        def __init__(self, store: Any, plan_id: int) -> None:
            super().__init__(store)
            self.plan_id = plan_id
            self.title = f"questions · P{plan_id}"
            self.empty = "No questions. Press a to record an ambiguity."

        @property
        def source_parent(self) -> tuple[str, int] | None:
            return ("plan", self.plan_id)

        def load_entries(self) -> list[HubEntry]:
            out: list[HubEntry] = []
            questions = services.list_questions(self.store, self.plan_id, "all")
            open_count = sum(1 for question in questions if question.status == "open")
            for question in questions:
                body = (
                    f"Q{question.id} · {question.status}\n"
                    f"{escape_markup(question.text)}\n\n"
                    f"readiness: {open_count} open question(s) block plan ready"
                )
                if question.resolution:
                    body += f"\nresolution: {escape_markup(question.resolution)}"
                out.append(
                    HubEntry(question.id, f"Q{question.id} {question.status} {question.text}", body)
                )
            return out

        def add(self) -> None:
            def cb(text: str | None) -> None:
                if not text:
                    return
                services.add_question(self.store, self.plan_id, text, actor="tui")
                self._reload()

            self.app.push_screen(
                FilterPromptScreen("Add question", "what is ambiguous?", "Add"), cb
            )

        def toggle(self) -> None:
            entry = self._selected()
            if entry is None:
                self._notify_empty()
                return
            question = self.store.get_question(entry.oid)
            if question is None:
                return
            if question.status == "open":
                services.resolve_question(self.store, entry.oid, actor="tui")
            else:
                services.reopen_question(self.store, entry.oid, actor="tui")
            self._reload()

        def open_entry(self, entry: HubEntry) -> None:
            self.toggle()

    class ReferencesHub(HubScreen):
        """External references on one plan: link, open, and unlink."""

        kind = "references"

        def __init__(self, store: Any, plan_id: int) -> None:
            super().__init__(store)
            self.plan_id = plan_id
            self.title = f"references · P{plan_id}"
            self.empty = "No references. Press a to link an issue, epic, or doc."

        @property
        def source_parent(self) -> tuple[str, int] | None:
            return ("plan", self.plan_id)

        def load_entries(self) -> list[HubEntry]:
            out: list[HubEntry] = []
            for ref in services.list_refs(self.store, self.plan_id):
                label = ref.title or ref.url
                body = (
                    f"R{ref.id} · {ref.kind}\n"
                    f"provider {escape_markup(ref.provider)}\n"
                    f"title    {escape_markup(ref.title or '—')}\n"
                    f"url      {escape_markup(ref.url)}"
                )
                out.append(HubEntry(ref.id, f"R{ref.id} {ref.kind} {label}", body))
            return out

        def add(self) -> None:
            def cb(text: str | None) -> None:
                if not text:
                    return
                try:
                    services.link_ref(self.store, self.plan_id, text.strip(), actor="tui")
                except (ValueError, KeyError) as exc:
                    self.notify(f"error: {exc}", timeout=4)
                    return
                self._reload()

            self.app.push_screen(FilterPromptScreen("Link reference", "https://…", "Link"), cb)

        def delete_row(self) -> None:
            entry = self._selected()
            if entry is None:
                self._notify_empty()
                return

            def cb(confirmed: bool | None) -> None:
                if confirmed:
                    services.unlink_ref(self.store, self.plan_id, ref_id=entry.oid, actor="tui")
                    self._reload()

            self.app.push_screen(ConfirmScreen(f"Unlink reference R{entry.oid}?"), cb)

        def open_value(self) -> None:
            entry = self._selected()
            if entry is None:
                self._notify_empty()
                return
            for ref in services.list_refs(self.store, self.plan_id):
                if ref.id == entry.oid:
                    webbrowser.open(ref.url)
                    self.notify(f"opened {ref.url}", timeout=4)
                    return

        def open_entry(self, entry: HubEntry) -> None:
            self.open_value()
