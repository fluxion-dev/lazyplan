"""In-memory tree filtering: status, source, text, and provenance counts."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from ... import services
from ... import stats as stats_mod
from ...models import Milestone, Plan, Status, Task

if TYPE_CHECKING:
    from ..app import LazyplanApp


class TreeFilter:
    """Filter one unfiltered services.tree() snapshot."""

    def __init__(self, app: LazyplanApp) -> None:
        self.app = app

    # -- filtering ---------------------------------------------------------
    def status_tree(
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

    def source_match(self, stats: tuple[int, int, int, int]) -> bool:
        commits, pulls, stale, repos = stats
        source_filter = self.app.source_filter
        if source_filter == "linked":
            return commits > 0 or pulls > 0 or repos > 0
        if source_filter == "pr":
            return pulls > 0
        if source_filter == "stale":
            return stale > 0
        if source_filter == "unlinked":
            return commits == 0 and pulls == 0 and repos == 0
        return True

    def filter_tasks(
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

    def source_stats(
        self,
        base: list[tuple[Plan, list[tuple[Milestone, list[Task]]]]],
    ) -> dict[tuple[str, int], tuple[int, int, int, int]]:
        """Direct plus descendant provenance counts per visible row."""
        store = self.app.store
        vcs = store.vcs_links_map()
        forge = store.forge_links_map()
        repos = store.repos_map()

        def direct(kind: str, oid: int) -> tuple[int, int, int, int]:
            links = vcs.get((kind, oid), [])
            pulls = forge.get((kind, oid), [])
            return (
                len(links),
                len(pulls),
                sum(1 for link in links if link.stale) + sum(1 for pull in pulls if pull.stale),
                len(repos.get((kind, oid), [])),
            )

        out: dict[tuple[str, int], tuple[int, int, int, int]] = {}
        for plan, milestones in base:
            pc, pp, ps, pr = direct("plan", plan.id)
            plan_repos = pr
            for milestone, tasks in milestones:
                mc, mp, ms, mr = direct("milestone", milestone.id)
                milestone_repos = mr or plan_repos
                for task in tasks:
                    tc, tp, ts, tr = direct("task", task.id)
                    task_repos = tr or milestone_repos
                    out[("task", task.id)] = (tc, tp, ts, task_repos)
                    mc, mp, ms = mc + tc, mp + tp, ms + ts
                    milestone_repos = max(milestone_repos, task_repos)
                out[("milestone", milestone.id)] = (mc, mp, ms, milestone_repos)
                pc, pp, ps = pc + mc, pp + mp, ps + ms
                plan_repos = max(plan_repos, milestone_repos)
            out[("plan", plan.id)] = (pc, pp, ps, plan_repos)
        return out

    def filter_source_tree(
        self,
        base: list[tuple[Plan, list[tuple[Milestone, list[Task]]]]],
        stats: dict[tuple[str, int], tuple[int, int, int, int]],
    ) -> list[tuple[Plan, list[tuple[Milestone, list[Task]]]]]:
        """Keep rows whose cached provenance matches the active source filter."""
        source_filter = self.app.source_filter
        if source_filter == "all":
            return base
        if source_filter in ("claims", "blocked", "attention"):
            claims = self.app.store.claims_map()
            attention = (
                stats_mod.attention_ids(self.app.store) if source_filter == "attention" else set()
            )
            if source_filter == "claims":
                return self.filter_tasks(base, lambda task: task.id in claims)
            if source_filter == "blocked":
                return self.filter_tasks(base, lambda task: task.blocked)
            return self.filter_tasks(base, lambda task: task.id in attention)
        out: list[tuple[Plan, list[tuple[Milestone, list[Task]]]]] = []
        for plan, milestones in base:
            kept_ms: list[tuple[Milestone, list[Task]]] = []
            for milestone, tasks in milestones:
                kept_tasks = [
                    task
                    for task in tasks
                    if self.source_match(stats.get(("task", task.id), (0, 0, 0, 0)))
                ]
                if kept_tasks or self.source_match(
                    stats.get(("milestone", milestone.id), (0, 0, 0, 0))
                ):
                    kept_ms.append((milestone, kept_tasks))
            if kept_ms or self.source_match(stats.get(("plan", plan.id), (0, 0, 0, 0))):
                out.append((plan, kept_ms))
        return out

    def filtered_tree(
        self,
        base: list[tuple[Plan, list[tuple[Milestone, list[Task]]]]] | None = None,
    ) -> list[tuple[Plan, list[tuple[Milestone, list[Task]]]]]:
        app = self.app
        if base is None:
            base = services.tree(app.store, status=None, archived="hide")
            base = self.status_tree(base, app.status_filter)
            if not (app.show_all or app.filter_text.strip()):
                base = base[: services.DEFAULT_PLAN_LIMIT]
        if app.source_filter != "all":
            base = self.filter_source_tree(base, self.source_stats(base))
        query = app.filter_text.strip().lower()
        if not query:
            return base
        notes = app.store.notes_map()
        comments = app.store.comments_map()
        issues = app.store.issues_map()
        claims = app.store.claims_map()

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
        for plan, milestones in base:
            if query in blob("plan", plan):
                filtered.append((plan, milestones))
                continue
            kept_ms: list[tuple[Milestone, list[Task]]] = []
            for milestone, tasks in milestones:
                if query in blob("milestone", milestone):
                    kept_ms.append((milestone, list(tasks)))
                    continue
                hits = [task for task in tasks if query in blob("task", task)]
                if hits:
                    kept_ms.append((milestone, hits))
            if kept_ms:
                filtered.append((plan, kept_ms))
        return filtered
