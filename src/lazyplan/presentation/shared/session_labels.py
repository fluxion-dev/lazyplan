"""Shared session labels for the pane, hub, and CLI."""

from __future__ import annotations

from typing import Protocol

from ...core.entities import Plan, Session
from ...core.policies.provenance import branch_ref


class PlanNamesPort(Protocol):
    """The plan list a session label needs for titles."""

    def list_plans(self, archived: str = "show") -> list[Plan]: ...


def plan_names(port: PlanNamesPort) -> dict[int, str]:
    """Plan id to title for every plan the journal knows."""
    return {plan.id: plan.name for plan in port.list_plans()}


def plan_label(session: Session, title: str = "", empty: str = "no plan") -> str:
    """Plan id with its title, or *empty* when the row has no plan."""
    if session.plan_id is None:
        return empty
    label = f"P{session.plan_id}"
    return f"{label} {title}" if title else label


def task_label(session: Session) -> str:
    """Task id encoded in the branch name, else an empty string."""
    ref = branch_ref(session.branch)
    return f"T{ref[1]}" if ref is not None and ref[0] == "task" else ""


def branch_label(session: Session, empty: str = "no branch") -> str:
    """Branch name, or *empty* when the row has none."""
    return session.branch if session.branch else empty
