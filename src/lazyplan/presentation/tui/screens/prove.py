"""Open the prove form and validate its fields for any screen."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .... import services
from ....core.ports.provenance import ProvenancePort
from .forms import ProveScreen


def prove_dialog(
    screen: Any,
    store: ProvenancePort,
    kind: str,
    oid: int,
    on_done: Callable[[int, services.ProofResult], None],
) -> None:
    """Open the evidence form for the first open criterion on a row."""
    items = store.list_criteria(kind, oid)
    if not items:
        screen.notify("this row has no criteria", timeout=3)
        return
    open_items = [criterion for criterion in items if not criterion.done]
    default = (open_items or items)[0].id

    def cb(data: dict[str, str] | None) -> None:
        if not data:
            return
        try:
            criterion_id = int(data.get("criterion", ""))
        except ValueError:
            screen.notify("criterion id must be a number", timeout=3)
            return
        exit_text = data.get("exit", "").strip()
        try:
            exit_code = int(exit_text) if exit_text else None
        except ValueError:
            screen.notify("exit code must be a number", timeout=3)
            return
        task_text = data.get("task", "").strip()
        try:
            task_id = int(task_text) if task_text else None
        except ValueError:
            screen.notify("task id must be a number", timeout=3)
            return
        try:
            result = services.prove(
                store,
                criterion_id,
                command=data.get("command", ""),
                exit_code=exit_code,
                commit_sha=data.get("commit", ""),
                note=data.get("note", ""),
                task_id=task_id,
                actor="tui",
            )
        except (ValueError, KeyError) as exc:
            screen.notify(f"error: {exc}", timeout=5)
            return
        on_done(criterion_id, result)

    screen.app.push_screen(
        ProveScreen({"criterion": str(default)}, context=f"{kind} {oid}"),
        cb,
    )
