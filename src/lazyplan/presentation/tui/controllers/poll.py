"""External-change polling: worker reads, compare, and coalesce.

Split from ``tree.py`` so the controller stays inside the module budget. The
mixin reads both fingerprints on a worker thread, applies live state to the
agents pane, and coalesces structural updates behind one short timer.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..app import LazyplanApp

REAP_INTERVAL = 60.0
COALESCE_SECONDS = 0.25


class PollMixin:
    """One in-flight fingerprint poll with a coalesced structural refresh."""

    app: LazyplanApp
    _poll_worker: Any
    _flush_timer: Any
    _pending_structural: bool
    _pending_note: str
    _last_reap: float

    def poll(self) -> None:
        """Start one background read of the poll keys, if none is pending."""
        if self._apply_dirty():
            return
        if self._poll_worker is not None and not self._poll_worker.is_finished:
            return
        self._poll_worker = self.app.run_worker(
            self._poll_in_worker,
            name="poll",
            group="poll",
            thread=True,
            exit_on_error=False,
        )

    def poll_now(self) -> None:
        """Read and apply one poll on the calling thread; tests use this."""
        if self._apply_dirty():
            return
        state = self._read_state()
        if state is not None:
            self._apply_poll(*state)

    def _poll_in_worker(self) -> None:
        state = self._read_state()
        if state is None:
            return
        try:
            self.app.call_from_thread(self._apply_poll, *state)
        except Exception:
            pass

    def _read_state(self) -> tuple | None:
        """Read both poll keys and the newest event; never touches widgets."""
        app = self.app
        now = time.time()
        if now - self._last_reap >= REAP_INTERVAL:
            self._last_reap = now
            try:
                app.store.reap_idle_sessions(now=now)
            except Exception:
                pass
        try:
            structural = app.store.fingerprint()
            live = app.store.live_fingerprint()
        except Exception:
            return None
        events = app.store.feed(1) if structural != app._fp else []
        return (structural, live, events)

    def _apply_dirty(self) -> bool:
        """Apply a change deferred by a modal once that modal closes."""
        app = self.app
        if not app._dirty_external or len(app.screen_stack) > 1:
            return False
        app._dirty_external = False
        self._pending_structural = False
        app.rev += 1
        return True

    def _apply_poll(self, fingerprint: tuple, live: tuple, events: list[dict]) -> None:
        """Compare one worker result and schedule the cheapest refresh."""
        app = self.app
        structural_changed = fingerprint != app._fp
        live_changed = live != app._live_fp
        if not structural_changed and not live_changed:
            return
        app._fp = fingerprint
        app._live_fp = live
        if live_changed:
            app.update_agents()
        if not structural_changed:
            return
        note = "db changed — refreshed"
        if events:
            event = events[0]
            event_id = int(event.get("id") or 0)
            if event_id > app._last_event_id:
                app._last_event_id = event_id
                note = f"[{event['actor']}] {event['kind']}/{event['action']}: {event['detail']}"
                try:
                    app.notify(note, timeout=4)
                except Exception:
                    pass
        self._pending_note = note
        self._pending_structural = True
        self._schedule_flush()

    def _schedule_flush(self) -> None:
        """Coalesce a burst of structural writes behind one short timer."""
        if self._flush_timer is not None:
            return
        self._flush_timer = self.app.set_timer(COALESCE_SECONDS, self._flush_soon)

    def _flush_soon(self) -> None:
        self._flush_timer = None
        self._flush_structural()

    def _flush_structural(self) -> None:
        """Rebuild the tree once for every change in the coalescing window."""
        if not self._pending_structural:
            return
        app = self.app
        if len(app.screen_stack) > 1:
            app._dirty_external = True
            return
        self._pending_structural = False
        app._pending_note = self._pending_note
        app.rev += 1
