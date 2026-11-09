"""Question actions opened from the plan detail page."""

from __future__ import annotations

from typing import Any

from .... import services
from .forms import FilterPromptScreen


def _plan_id(screen: Any) -> int | None:
    if screen.dkind == "plan":
        return int(screen.doid)
    if screen.dkind == "milestone":
        return int(screen._obj().get("plan_id") or 0) or None
    milestone = screen._dstore.get_milestone(int(screen._obj().get("milestone_id", 0)))
    return milestone.plan_id if milestone is not None else None


def add_question(screen: Any) -> None:
    plan_id = _plan_id(screen)
    if plan_id is None:
        screen.notify("this row has no owning plan", timeout=3)
        return

    def cb(text: str | None) -> None:
        if not text:
            return
        question = services.add_question(screen._dstore, plan_id, text, actor="tui")
        screen._reload()
        screen.notify(f"Q{question.id} added", timeout=4)

    screen.app.push_screen(
        FilterPromptScreen(
            title=f"Add question to P{plan_id}",
            placeholder="what is ambiguous?",
            submit_label="Add",
        ),
        cb,
    )


def resolve_question(screen: Any) -> None:
    plan_id = _plan_id(screen)
    if plan_id is None:
        screen.notify("this row has no owning plan", timeout=3)
        return

    def cb(text: str | None) -> None:
        if not text:
            return
        try:
            question_id = int(text)
        except ValueError:
            screen.notify("question id must be a number", timeout=3)
            return
        services.resolve_question(screen._dstore, question_id, actor="tui")
        screen._reload()
        screen.notify(f"Q{question_id} resolved", timeout=4)

    screen.app.push_screen(
        FilterPromptScreen(
            title=f"Resolve a question on P{plan_id} (id)",
            placeholder="question id",
            submit_label="Resolve",
        ),
        cb,
    )


def reopen_question(screen: Any) -> None:
    if _plan_id(screen) is None:
        screen.notify("this row has no owning plan", timeout=3)
        return

    def cb(text: str | None) -> None:
        if not text:
            return
        try:
            question_id = int(text)
        except ValueError:
            screen.notify("question id must be a number", timeout=3)
            return
        services.reopen_question(screen._dstore, question_id, actor="tui")
        screen._reload()
        screen.notify(f"Q{question_id} reopened", timeout=4)

    screen.app.push_screen(
        FilterPromptScreen(
            title="Reopen a question (id)",
            placeholder="question id",
            submit_label="Reopen",
        ),
        cb,
    )


class QuestionActionsMixin:
    """Detail bindings for the plan question actions."""

    def action_add_question(self: Any) -> None:
        if self._editing:
            self.notify("save or cancel first")
            return
        add_question(self)

    def action_resolve_question(self: Any) -> None:
        if self._editing:
            self.notify("save or cancel first")
            return
        resolve_question(self)

    def action_reopen_question(self: Any) -> None:
        if self._editing:
            self.notify("save or cancel first")
            return
        reopen_question(self)
