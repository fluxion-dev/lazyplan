"""Demo seed: one project, two stories, a few tasks with dates for gantt."""

from __future__ import annotations

from .store import Store


def seed(store: Store) -> None:
    """Insert the demo project, stories, and tasks into an empty store."""
    if store.list_projects():
        print("db already has projects, skipping seed")
        return
    p = store.add_project(
        "Website relaunch",
        "Marketing site overhaul",
        start_date="2026-10-20",
        end_date="2026-12-15",
    )
    s1 = store.add_story(
        p.id,
        "Public homepage",
        "Hero + signup flow",
        start_date="2026-10-20",
        end_date="2026-11-10",
    )
    s2 = store.add_story(
        p.id,
        "Docs portal",
        "Migrate docs to new theme",
        start_date="2026-11-01",
        end_date="2026-12-01",
    )
    store.add_task(s1.id, "Design hero section", estimate="3d")
    store.add_task(s1.id, "Wire signup API", estimate="2d")
    store.add_task(s2.id, "Port markdown content", estimate="5d")
    print(f"seeded project #{p.id} with 2 stories, 3 tasks")
