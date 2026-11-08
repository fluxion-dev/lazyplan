"""Let deferred tree highlights land before a test sets the selection.

Textual's idle wait samples the process clock, which ticks about every 16 ms
on Windows, so a bare pause can return before the tree's after-refresh
highlight runs and overwrites the selection a test just set.
"""

from __future__ import annotations

from typing import Any


async def settle(pilot: Any) -> None:
    """Pause on real time until queued highlights have run."""
    for _ in range(3):
        await pilot.pause(0.05)


async def walk_route(pilot: Any, keys: tuple[str, ...]) -> list[str]:
    """Press one route from the main tree and record each screen name."""
    seen = ["tree"]
    for key in keys:
        await pilot.press(key)
        await pilot.pause()
        seen.append(str(getattr(pilot.app.screen, "navigation_name", "tree")))
    return seen
