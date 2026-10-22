"""Demo seed: one plan with why/what, acceptance criteria, and work."""

from __future__ import annotations

from .store import Store


def seed(store: Store) -> None:
    """Insert the demo plan, milestones, and tasks into an empty store."""
    if store.list_plans():
        print("db already has plans, skipping seed")
        return
    p = store.add_plan(
        "Website relaunch",
        "Marketing site overhaul",
        goal="Lift signup conversion with a faster, clearer homepage",
    )
    store.add_criteria("plan", p.id, "Homepage loads in under 2s")
    store.add_criteria("plan", p.id, "Signup flow works end to end")
    s1 = store.add_milestone(p.id, "Public homepage", "Hero + signup flow")
    s2 = store.add_milestone(p.id, "Docs portal", "Migrate docs to new theme")
    store.add_task(s1.id, "Design hero section")
    store.add_task(s1.id, "Wire signup API")
    store.add_task(s2.id, "Port markdown content")
    print(f"seeded plan #{p.id} with 2 milestones, 3 tasks")
