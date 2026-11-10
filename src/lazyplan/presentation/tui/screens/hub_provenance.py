"""Provenance and activity hubs: pull requests and the feed."""

from __future__ import annotations

import webbrowser
from typing import Any

from .... import services
from ...shared.design import escape_markup
from ..views.provenance import event_body, event_label, event_target
from .forms import ConfirmScreen, FilterPromptScreen

try:
    from textual.binding import Binding

    from .hub import HubEntry, HubScreen

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover - stdlib-only interpreter
    _TEXTUAL_OK = False

try:
    from ....infrastructure.forge import parse_pull_url
except ImportError:  # pragma: no cover - stdlib-only interpreter
    parse_pull_url = None  # type: ignore[assignment]


def scope_parents(store: Any, kind: str, oid: int) -> list[tuple[str, int]]:
    """Direct row plus descendant rows whose links the hub aggregates."""
    out: list[tuple[str, int]] = [(kind, oid)]
    if kind == "milestone":
        out.extend(("task", task.id) for task in store.list_tasks(oid))
    elif kind == "plan":
        for milestone in store.list_milestones(oid):
            out.append(("milestone", milestone.id))
            out.extend(("task", task.id) for task in store.list_tasks(milestone.id))
    return out


if _TEXTUAL_OK:

    class PullRequestHub(HubScreen):
        """Cached pull requests for one row and its descendants."""

        kind = "pull_requests"

        def __init__(self, store: Any, kind: str, oid: int) -> None:
            super().__init__(store)
            self.parent_kind = kind
            self.parent_id = oid
            self.title = f"pull requests · {kind} #{oid}"
            self.empty = "No pull requests. Press a to link a URL or r to refresh."
            self._rows: list[tuple[str, int, Any]] = []

        @property
        def source_parent(self) -> tuple[str, int]:
            return (self.parent_kind, self.parent_id)

        def load_entries(self) -> list[HubEntry]:
            self._rows = []
            seen: set[tuple[str, int, int]] = set()
            for parent_kind, parent_id in scope_parents(
                self.store, self.parent_kind, self.parent_id
            ):
                for link in self.store.list_forge_links(parent_kind, parent_id, kind="pull"):
                    key = (parent_kind, parent_id, int(link.number))
                    if key in seen:
                        continue
                    seen.add(key)
                    self._rows.append((parent_kind, parent_id, link))
            out: list[HubEntry] = []
            for parent_kind, parent_id, link in self._rows:
                state = str(link.state or "unknown")
                stale = " [red]stale[/]" if link.stale else ""
                checks = f" · checks {link.checks}" if link.checks and link.checks != "none" else ""
                reviews = (
                    f" · reviews {link.reviews}" if link.reviews and link.reviews != "none" else ""
                )
                body = (
                    f"PR #{link.number} · {state}{stale}\n"
                    f"owner    {parent_kind} #{parent_id}\n"
                    f"title    {escape_markup(link.title or '—')}\n"
                    f"base     {escape_markup(link.base_ref or '—')}\n"
                    f"head     {escape_markup(link.head_ref or '—')}\n"
                    f"checks   {link.checks or 'none'} · reviews {link.reviews or 'none'}\n"
                    f"merged   {link.merged_at or '—'}\n"
                    f"url      {link.url or '—'}"
                )
                out.append(
                    HubEntry(
                        int(link.number),
                        f"⇄ PR #{link.number} {state}{checks}{reviews}{stale}",
                        body,
                        "pull",
                        f"{parent_kind}:{parent_id}",
                    )
                )
            return out

        def add(self) -> None:
            def cb(text: str | None) -> None:
                if not text:
                    return
                if parse_pull_url is None:
                    self.notify("GitHub support unavailable", timeout=3)
                    return
                parsed = parse_pull_url(text.strip())
                if parsed is None:
                    self.notify("not a GitHub pull request URL", timeout=4)
                    return
                _ref, number = parsed
                self.store.link_forge(
                    self.parent_kind,
                    self.parent_id,
                    number,
                    provider="github",
                    kind="pull",
                    url=text.strip(),
                    title=f"PR #{number}",
                    actor="tui",
                )
                self._reload()

            self.app.push_screen(
                FilterPromptScreen("Link pull request", "https://github.com/…/pull/N", "Link"),
                cb,
            )

        def delete_row(self) -> None:
            selected = self._selected_row()
            if selected is None:
                self._notify_empty()
                return
            parent_kind, parent_id, link = selected

            def cb(confirmed: bool | None) -> None:
                if confirmed:
                    self.store.unlink_forge(parent_kind, parent_id, int(link.number), actor="tui")
                    self._reload()

            self.app.push_screen(ConfirmScreen(f"Unlink PR #{link.number}?"), cb)

        def _selected_row(self) -> tuple[str, int, Any] | None:
            entry = self._selected()
            if entry is None:
                return None
            return next(
                (
                    row
                    for row in self._rows
                    if int(row[2].number) == entry.oid and f"{row[0]}:{row[1]}" == entry.ref
                ),
                None,
            )

        def open_value(self) -> None:
            selected = self._selected_row()
            if selected is None:
                self._notify_empty()
                return
            link = selected[2]
            if not link.url:
                self.notify("no pull request URL", timeout=3)
                return
            webbrowser.open(link.url)
            self.notify(f"opened {link.url}", timeout=4)

        def open_entry(self, entry: HubEntry) -> None:
            self.open_value()

        def action_refresh(self) -> None:
            """Refresh cached pull requests; this is the only network path."""
            self.notify("refreshing pull requests…", timeout=2)
            self.run_worker(self._refresh_worker, thread=True, exclusive=True)

        def _refresh_worker(self) -> None:
            try:
                stats = services.refresh_forge(
                    self.store, self.parent_kind, self.parent_id, actor="tui"
                )
            except Exception as exc:  # keep the screen alive offline
                self.app.call_from_thread(
                    self.notify, f"refresh failed: {exc}", severity="warning", timeout=5
                )
                return
            self.app.call_from_thread(
                self.notify,
                f"linked {stats.get('linked', 0)} PRs · {stats.get('stale', 0)} cached",
                timeout=5,
            )
            self.app.call_from_thread(self._reload)

    class ActivityHub(HubScreen):
        """Recent feed rows with jump targets."""

        kind = "activity"
        BINDINGS = [
            Binding("f", "filter_actor", "Actor"),
            Binding("K", "filter_kind", "Kind"),
        ]

        def __init__(self, store: Any, limit: int = 100) -> None:
            super().__init__(store)
            self.limit = limit
            self.title = "activity"
            self.empty = "No activity yet."
            self.actor_filter = ""
            self.kind_filter = ""

        @property
        def source_parent(self) -> tuple[str, int] | None:
            return None

        def load_entries(self) -> list[HubEntry]:
            rows = self.store.feed(self.limit)
            if self.actor_filter:
                rows = [row for row in rows if str(row.get("actor")) == self.actor_filter]
            if self.kind_filter:
                rows = [row for row in rows if str(row.get("kind")) == self.kind_filter]
            out: list[HubEntry] = []
            for event in rows:
                target = event_target(event)
                ref = f"{target[0]}:{target[1]}" if target else ""
                out.append(
                    HubEntry(
                        int(event.get("id", 0)),
                        event_label(event),
                        event_body(event),
                        "event",
                        ref,
                    )
                )
            return out

        def action_filter_actor(self) -> None:
            def cb(text: str | None) -> None:
                self.actor_filter = (text or "").strip().lstrip("@")
                self._reload()

            self.app.push_screen(
                FilterPromptScreen("Filter actor", "actor name (blank for all)", "Filter"),
                cb,
            )

        def action_filter_kind(self) -> None:
            def cb(text: str | None) -> None:
                self.kind_filter = (text or "").strip()
                self._reload()

            self.app.push_screen(
                FilterPromptScreen("Filter kind", "plan, task, vcs… (blank for all)", "Filter"),
                cb,
            )

        def open_entry(self, entry: HubEntry) -> None:
            if not entry.ref:
                self.notify("this event has no row target", timeout=3)
                return
            kind, raw = entry.ref.split(":", 1)
            try:
                oid = int(raw)
            except ValueError:
                return
            if kind in ("plan", "milestone", "task"):
                opener = getattr(self.app, "select_row", None)
                if callable(opener):
                    opener(kind, oid)
                    return
                self.notify(f"{kind} #{oid}", timeout=3)
                return
            self.notify(f"{kind} #{oid}", timeout=3)


__all__ = ["ActivityHub", "PullRequestHub", "scope_parents"]
