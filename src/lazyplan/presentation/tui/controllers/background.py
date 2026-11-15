"""One worker path for the app's read-only startup checks."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from ..app import LazyplanApp

Result = TypeVar("Result")


def run_off_thread(
    app: LazyplanApp,
    work: Callable[[], Result],
    done: Callable[[Result], None],
    group: str,
) -> None:
    """Run *work* on a worker thread, then hand its result to *done*.

    A failed check is dropped: neither setup nor the health prompt may break
    the screen, and the app thread only ever applies a completed answer.
    """

    def worker() -> None:
        try:
            result = work()
        except Exception:  # noqa: BLE001 - a failed check must never break the TUI
            return
        app.call_from_thread(done, result)

    app.run_worker(worker, thread=True, group=group)
