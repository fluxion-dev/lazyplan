"""Textual app: filters."""

from __future__ import annotations

from collections.abc import Callable

try:
    from textual import events, on  # noqa: F401
    from textual.app import App, ComposeResult  # noqa: F401
    from textual.binding import Binding  # noqa: F401
    from textual.containers import Horizontal, Vertical, VerticalScroll  # noqa: F401
    from textual.reactive import reactive  # noqa: F401
    from textual.widgets import Label, Static, Tree  # noqa: F401
    from textual.widgets.tree import TreeNode  # noqa: F401

    from ..tree_nav import NavTree  # noqa: F401

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from .. import services
from .. import stats as stats_mod
from ..design import (
    truncate,
)
from ..models import Milestone, Plan, Status, Task
from ..repo import repo_label
from .base import AppBase
from .screens import (
    FilterPromptScreen,
)

STATUS_CYCLE: list[Status | None] = [None, Status.TODO, Status.DOING, Status.DONE]
DOUBLE_CLICK_WINDOW = 0.5  # seconds between two clicks on one row


if _TEXTUAL_OK:

    class FilterMixin(AppBase):
        SOURCE_FILTERS = (
            "all",
            "linked",
            "pr",
            "stale",
            "unlinked",
            "claims",
            "blocked",
            "attention",
        )
        """Filters behavior."""

        def _open_filter_prompt(self) -> None:
            """Prompt for tree filter text; empty clears the filter."""

            def cb(text: str | None) -> None:
                if text is None:
                    return
                self.filter_text = text
                self._pending_note = f"filter: {text}" if text else "filter cleared"
                try:
                    self.rev += 1
                except Exception:
                    self.refresh_all(self._pending_note)

            self.push_screen(FilterPromptScreen(), cb)

        def _status_tree(
            self,
            base: list[tuple[Plan, list[tuple[Milestone, list[Task]]]]],
            status: Status | None,
        ) -> list[tuple[Plan, list[tuple[Milestone, list[Task]]]]]:
            """Apply the status filter in memory to one unfiltered snapshot."""
            if status is None:
                return base
            out: list[tuple[Plan, list[tuple[Milestone, list[Task]]]]] = []
            for plan, milestones in base:
                kept_ms: list[tuple[Milestone, list[Task]]] = []
                for milestone, tasks in milestones:
                    kept = [task for task in tasks if task.status == status]
                    if milestone.status != status and not kept:
                        continue
                    kept_ms.append((milestone, kept))
                if plan.status == status or kept_ms:
                    out.append((plan, kept_ms))
            return out

        def _source_match(self, stats: tuple[int, int, int, int]) -> bool:
            commits, pulls, stale, repos = stats
            if self.source_filter == "linked":
                return commits > 0 or pulls > 0 or repos > 0
            if self.source_filter == "pr":
                return pulls > 0
            if self.source_filter == "stale":
                return stale > 0
            if self.source_filter == "unlinked":
                return commits == 0 and pulls == 0 and repos == 0
            return True

        def _filter_tasks(
            self,
            base: list[tuple[Plan, list[tuple[Milestone, list[Task]]]]],
            keep: Callable[[Task], bool],
        ) -> list[tuple[Plan, list[tuple[Milestone, list[Task]]]]]:
            """Keep tasks matching a predicate plus their parent context."""
            out: list[tuple[Plan, list[tuple[Milestone, list[Task]]]]] = []
            for plan, milestones in base:
                kept_milestones: list[tuple[Milestone, list[Task]]] = []
                for milestone, tasks in milestones:
                    kept = [task for task in tasks if keep(task)]
                    if kept:
                        kept_milestones.append((milestone, kept))
                if kept_milestones:
                    out.append((plan, kept_milestones))
            return out

        def action_filter_status(self) -> None:
            i = STATUS_CYCLE.index(self.status_filter)
            self.status_filter = STATUS_CYCLE[(i + 1) % len(STATUS_CYCLE)]
            self.refresh_all(
                f"status filter: {self.status_filter.value if self.status_filter else 'all'}"
            )

        def action_toggle_show_all(self) -> None:
            self.show_all = not self.show_all
            self.refresh_all("showing all plans" if self.show_all else "showing recent plans")

        def _refresh_status(self, note: str = "") -> None:
            """Update only the statusbar, without rebuilding the tree."""
            try:
                self.query_one("#status", Label).update(
                    self._status_text(self.store.counts(), note)
                )
            except Exception:
                pass

        def _source_stats(
            self, base: list[tuple[Plan, list[tuple[Milestone, list[Task]]]]]
        ) -> dict[tuple[str, int], tuple[int, int, int, int]]:
            """Direct plus descendant provenance counts per visible row."""
            vcs = self.store.vcs_links_map()
            forge = self.store.forge_links_map()
            repos = self.store.repos_map()

            def direct(kind: str, oid: int) -> tuple[int, int, int, int]:
                links = vcs.get((kind, oid), [])
                pulls = forge.get((kind, oid), [])
                return (
                    len(links),
                    len(pulls),
                    sum(1 for link in links if link.stale) + sum(1 for link in pulls if link.stale),
                    len(repos.get((kind, oid), [])),
                )

            stats: dict[tuple[str, int], tuple[int, int, int, int]] = {}
            for plan, milestones in base:
                pc, pp, ps, pr = direct("plan", plan.id)
                plan_repos = pr
                for milestone, tasks in milestones:
                    mc, mp, ms, mr = direct("milestone", milestone.id)
                    milestone_repos = mr or plan_repos
                    for task in tasks:
                        tc, tp, ts, tr = direct("task", task.id)
                        task_repos = tr or milestone_repos
                        stats[("task", task.id)] = (tc, tp, ts, task_repos)
                        mc, mp, ms = mc + tc, mp + tp, ms + ts
                        milestone_repos = max(milestone_repos, task_repos)
                    stats[("milestone", milestone.id)] = (mc, mp, ms, milestone_repos)
                    pc, pp, ps = pc + mc, pp + mp, ps + ms
                    plan_repos = max(plan_repos, milestone_repos)
                stats[("plan", plan.id)] = (pc, pp, ps, plan_repos)
            return stats

        def _status_text(self, counts: dict[str, int], note: str) -> str:
            """Human counts, filter state, update notice, and the latest event."""
            open_tasks = counts["tasks"] - counts["tasks_done"]
            bits = [
                repo_label(self.store.path),
                f"{counts['plans']} plans",
                f"{open_tasks} open",
                f"{counts['plans_doing']} doing",
            ]
            attention = len(stats_mod.attention_ids(self.store))
            if attention:
                bits.append(f"attention {attention}")
            if self.marked:
                bits.append(f"marked {len(self.marked)}")
            if self.status_filter is not None:
                bits.append(f"status {self.status_filter.value}")
            if self.source_filter != "all":
                bits.append(f"source {self.source_filter}")
            if self.filter_text.strip():
                bits.append(f'filter "{self.filter_text.strip()}"')
            if not self.show_all:
                bits.append(f"recent {services.DEFAULT_PLAN_LIMIT}")
            if self._update_notice is not None:
                bits.append("update available")
            text = " · ".join(bits)
            if note:
                text += f" — {note}"
            events = self.store.feed(1)
            if events:
                event = events[0]
                text += f" · last: {event['actor']} {event['kind']}/{event['action']}: {event['detail']}"
            return truncate(text, max(10, self.size.width - 2))

        def action_filter_text(self) -> None:
            """Prompt for filter text (slash)."""
            self._open_filter_prompt()

        def _filter_source_tree(
            self,
            base: list[tuple[Plan, list[tuple[Milestone, list[Task]]]]],
            stats: dict[tuple[str, int], tuple[int, int, int, int]],
        ) -> list[tuple[Plan, list[tuple[Milestone, list[Task]]]]]:
            """Keep rows whose cached provenance matches the active source filter."""
            if self.source_filter == "all":
                return base
            if self.source_filter in ("claims", "blocked", "attention"):
                claims = self.store.claims_map()
                attention = (
                    stats_mod.attention_ids(self.store)
                    if self.source_filter == "attention"
                    else set()
                )
                if self.source_filter == "claims":
                    return self._filter_tasks(base, lambda task: task.id in claims)
                if self.source_filter == "blocked":
                    return self._filter_tasks(base, lambda task: task.blocked)
                return self._filter_tasks(base, lambda task: task.id in attention)
            out = []
            for plan, milestones in base:
                kept_ms: list[tuple[Milestone, list[Task]]] = []
                for milestone, tasks in milestones:
                    kept_tasks = [
                        task
                        for task in tasks
                        if self._source_match(stats.get(("task", task.id), (0, 0, 0, 0)))
                    ]
                    if kept_tasks or self._source_match(
                        stats.get(("milestone", milestone.id), (0, 0, 0, 0))
                    ):
                        kept_ms.append((milestone, kept_tasks))
                if kept_ms or self._source_match(stats.get(("plan", plan.id), (0, 0, 0, 0))):
                    out.append((plan, kept_ms))
            return out

        def _filtered_tree(
            self,
            base: list[tuple[Plan, list[tuple[Milestone, list[Task]]]]] | None = None,
        ) -> list[tuple[Plan, list[tuple[Milestone, list[Task]]]]]:
            if base is None:
                base = services.tree(self.store, status=None, archived="hide")
                base = self._status_tree(base, self.status_filter)
                if not (self.show_all or self.filter_text.strip()):
                    base = base[: services.DEFAULT_PLAN_LIMIT]
            if self.source_filter != "all":
                base = self._filter_source_tree(base, self._source_stats(base))
            query = self.filter_text.strip().lower()
            if not query:
                return base
            notes = self.store.notes_map()
            comments = self.store.comments_map()
            issues = self.store.issues_map()
            claims = self.store.claims_map()

            def blob(kind: str, obj: Plan | Milestone | Task) -> str:
                if isinstance(obj, Plan):
                    bits = [obj.name, obj.description, obj.goal]
                elif isinstance(obj, Milestone):
                    bits = [obj.title, obj.description]
                else:
                    bits = [obj.title, obj.description, obj.blocked_reason]
                    claim = claims.get(obj.id)
                    if claim is not None:
                        bits.append(claim.actor)
                bits.extend(notes.get((kind, obj.id), []))
                bits.extend(comments.get((kind, obj.id), []))
                bits.extend(issues.get((kind, obj.id), []))
                return " ".join(str(bit) for bit in bits).lower()

            filtered: list[tuple[Plan, list[tuple[Milestone, list[Task]]]]] = []
            for p, milestones in base:
                if query in blob("plan", p):
                    filtered.append((p, milestones))
                    continue
                kept_ms: list[tuple[Milestone, list[Task]]] = []
                for s, tasks in milestones:
                    if query in blob("milestone", s):
                        kept_ms.append((s, list(tasks)))
                        continue
                    hits = [t for t in tasks if query in blob("task", t)]
                    if hits:
                        kept_ms.append((s, hits))
                if kept_ms:
                    filtered.append((p, kept_ms))
            return filtered

        def action_filter_source(self) -> None:
            """Cycle cached provenance filters."""
            index = self.SOURCE_FILTERS.index(self.source_filter)
            self.source_filter = self.SOURCE_FILTERS[(index + 1) % len(self.SOURCE_FILTERS)]
            self.refresh_all(f"source filter: {self.source_filter}")

        def action_clear_filter(self) -> None:
            if len(self.screen_stack) > 1:
                return
            if self.filter_text:
                self.filter_text = ""
                self._pending_note = "filter cleared"
                try:
                    self.rev += 1
                except Exception:
                    self.refresh_all("filter cleared")
                try:
                    self.query_one("#tree", Tree).focus()
                except Exception:
                    pass
