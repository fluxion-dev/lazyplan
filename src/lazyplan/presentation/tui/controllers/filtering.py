"""In-memory tree filtering: plan mode, text, and provenance counts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .... import services
from ....core.entities import Milestone, Plan, Status, Task
from ..state import PlanMode

if TYPE_CHECKING:
    from ..app import LazyplanApp


class TreeFilter:
    """Filter one unfiltered services.tree() snapshot."""

    def __init__(self, app: LazyplanApp) -> None:
        self.app = app

    def mode_tree(
        self,
        base: list[tuple[Plan, list[tuple[Milestone, list[Task]]]]],
        mode: PlanMode,
    ) -> list[tuple[Plan, list[tuple[Milestone, list[Task]]]]]:
        """Keep whole plan trees by mode; done plans sort last in Both."""
        if mode is PlanMode.ACTIVE:
            return [(plan, milestones) for plan, milestones in base if plan.status != Status.DONE]
        if mode is PlanMode.FINISHED:
            return [(plan, milestones) for plan, milestones in base if plan.status == Status.DONE]
        return sorted(base, key=lambda entry: entry[0].status == Status.DONE)

    def source_stats(
        self,
        base: list[tuple[Plan, list[tuple[Milestone, list[Task]]]]],
        vcs: dict | None = None,
        forge: dict | None = None,
        repos: dict | None = None,
    ) -> dict[tuple[str, int], tuple[int, int, int, int]]:
        """Direct plus descendant provenance counts per visible row."""
        store = self.app.store
        vcs = store.vcs_links_map() if vcs is None else vcs
        forge = store.forge_links_map() if forge is None else forge
        repos = store.repos_map() if repos is None else repos

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

    def filtered_tree(
        self,
        base: list[tuple[Plan, list[tuple[Milestone, list[Task]]]]] | None = None,
    ) -> list[tuple[Plan, list[tuple[Milestone, list[Task]]]]]:
        app = self.app
        if base is None:
            base = services.tree(app.store, status=None, archived="show")
        base = self.mode_tree(base, app.plan_mode)
        query = app.filter_text.strip().lower()
        if not query:
            return base
        notes = services.notes_map(app.store)
        comments = services.comments_map(app.store)
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
