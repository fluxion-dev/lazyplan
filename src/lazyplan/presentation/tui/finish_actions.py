"""Finish a task, prompting for a reason when a gate blocks it."""

from __future__ import annotations

from collections.abc import Callable

from ... import services
from .context import ContextMixin


class FinishMixin(ContextMixin):
    """Link commits and close a task through the finish gates."""

    def action_finish_task(self) -> None:
        task_id = self._selected_task()
        if task_id is None:
            return

        def attempt(reason: str = "") -> None:
            try:
                result = services.finish_task(
                    self.store,
                    task_id,
                    actor="tui",
                    require_pr=True,
                    require_checks=True,
                    require_evidence=True,
                    override=reason,
                )
            except services.GateError as exc:
                self._prompt_finish_reason(str(exc), attempt)
                return
            except (ValueError, KeyError) as exc:
                self.notify(str(exc), severity="error", timeout=5)
                return
            self._record_override("finish", f"T{task_id}", reason)
            state = "finished" if result.get("done") else "linked; tree is dirty"
            self.notify(f"T{task_id} {state}", timeout=4)
            self._saved("task finished")

        attempt()

    def _prompt_finish_reason(self, gate: str, attempt: Callable[[str], None]) -> None:
        self.prompt_reason(
            f"{gate}\nWhy override?",
            "reason for the finish override…",
            "Override",
            attempt,
            "a finish override needs a reason",
        )
