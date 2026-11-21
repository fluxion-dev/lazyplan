"""Shared helpers for mounted TUI tests: text capture and deferred work."""

from __future__ import annotations

import asyncio
import io
from typing import Any


def plain(markup: str) -> str:
    """Render Rich markup without writing to the platform console."""
    from rich.console import Console

    console = Console(record=True, width=400, force_terminal=False, file=io.StringIO())
    console.print(markup, end="")
    return console.export_text()


async def wait_for_flush(app: Any, pilot: Any, timeout: float = 2.0) -> None:
    """Wait for the coalesced poll flush to land instead of a fixed pause."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    controller = app.tree_controller
    while controller._flush_timer is not None:
        if loop.time() >= deadline:
            raise AssertionError("the coalesced flush did not land")
        await pilot.pause(0.01)


async def settle_reflow(app: Any, pilot: Any, timeout: float = 2.0) -> None:
    """Wait for the reflow a layout change queues, then settle the rows."""
    await pilot.pause()
    await pilot.pause()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    controller = app.tree_controller
    while controller._reflow_pending:
        if loop.time() >= deadline:
            raise AssertionError("the tree reflow did not land")
        await pilot.pause(0.01)
    controller.reflow()
    await pilot.pause()


async def wait_for_tree_resize(app: Any, pilot: Any, before: int, timeout: float = 2.0) -> None:
    """Wait for a layout change to give the tree a new width, then settle."""
    from textual.widgets import Tree

    tree = app.query_one("#tree", Tree)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while tree.size.width == before:
        if loop.time() >= deadline:
            raise AssertionError("the tree did not resize")
        await pilot.pause(0.01)
    await settle_reflow(app, pilot)
