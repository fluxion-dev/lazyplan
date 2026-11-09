"""Plan question actions: add, resolve, and reopen."""

from __future__ import annotations

from ... import services
from .context import ContextMixin
from .screens import FilterPromptScreen


class QuestionMixin(ContextMixin):
    """Record plan-level ambiguity and close it again."""

    def action_add_question(self) -> None:
        plan_id = self._plan_ctx()
        if plan_id is None:
            self.notify("select a plan first (questions are plan scope)")
            return

        def cb(text: str | None) -> None:
            if not text:
                return
            try:
                question = services.add_question(self.store, plan_id, text, actor="tui")
            except (ValueError, KeyError) as exc:
                self.notify(f"error: {exc}", timeout=5)
                return
            self.notify(f"Q{question.id} added to P{plan_id}", timeout=4)
            self._saved("question added")

        self.push_screen(
            FilterPromptScreen(
                title=f"Add question to P{plan_id}",
                placeholder="what is ambiguous?",
                submit_label="Add",
            ),
            cb,
        )

    def action_resolve_question(self) -> None:
        plan_id = self._plan_ctx()
        if plan_id is None:
            self.notify("select a plan first (questions are plan scope)")
            return

        def cb(text: str | None) -> None:
            if not text:
                return
            try:
                question_id = int(text)
            except ValueError:
                self.notify("question id must be a number", timeout=3)
                return
            try:
                services.resolve_question(self.store, question_id, actor="tui")
            except (ValueError, KeyError) as exc:
                self.notify(f"error: {exc}", timeout=5)
                return
            self.notify(f"Q{question_id} resolved", timeout=4)
            self._saved("question resolved")

        self.push_screen(
            FilterPromptScreen(
                title=f"Resolve a question on P{plan_id} (id)",
                placeholder="question id",
                submit_label="Resolve",
            ),
            cb,
        )

    def action_reopen_question(self) -> None:
        plan_id = self._plan_ctx()
        if plan_id is None:
            self.notify("select a plan first (questions are plan scope)")
            return

        def cb(text: str | None) -> None:
            if not text:
                return
            try:
                question_id = int(text)
            except ValueError:
                self.notify("question id must be a number", timeout=3)
                return
            try:
                services.reopen_question(self.store, question_id, actor="tui")
            except (ValueError, KeyError) as exc:
                self.notify(f"error: {exc}", timeout=5)
                return
            self.notify(f"Q{question_id} reopened", timeout=4)
            self._saved("question reopened")

        self.push_screen(
            FilterPromptScreen(
                title=f"Reopen a question on P{plan_id} (id)",
                placeholder="question id",
                submit_label="Reopen",
            ),
            cb,
        )
