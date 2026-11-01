"""Deterministic SVG snapshots for the main TUI surfaces (pytest-only)."""

from __future__ import annotations

import os
import tempfile
from unittest import mock

import pytest

from lazyplan import metrics
from lazyplan.store import Store
from lazyplan.tui import create_app
from lazyplan.tui.screens import DetailScreen, PaletteScreen
from lazyplan.tui.screens.source import SourceScreen

FIXED_START = 1_700_000_000.0
FIXED_NOW = FIXED_START + 30 * 86_400


@pytest.fixture()
def empty_app():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "empty.db")
        Store(db)
        yield create_app(db)


@pytest.fixture()
def data_app():
    real_snapshot = metrics.snapshot
    clock = {"now": FIXED_START}

    def tick() -> float:
        clock["now"] += 3_600
        return clock["now"]

    def frozen_snapshot(store, now=None, plan_id=None, scope_kind=None, scope_id=None):
        return real_snapshot(
            store,
            now=FIXED_NOW,
            plan_id=plan_id,
            scope_kind=scope_kind,
            scope_id=scope_id,
        )

    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "data.db")
        with mock.patch("lazyplan.store.base.time.time", side_effect=tick):
            store = Store(db)
            plan = store.add_plan("Plan title", "What we build", goal="Why we build")
            milestone = store.add_milestone(plan.id, "Milestone title", "Milestone details")
            task = store.add_task(milestone.id, "Task title", "Task details")
            store.add_criteria("plan", plan.id, "The plan is readable")
            store.add_criteria("task", task.id, "The task is proven")
        store = Store(db)
        with mock.patch("lazyplan.metrics.snapshot", side_effect=frozen_snapshot):
            yield create_app(db), store, plan.id, task.id


def test_main_shell_empty(snap_compare, empty_app) -> None:
    assert snap_compare(empty_app, terminal_size=(120, 40))


def test_help_screen(snap_compare, data_app) -> None:
    app, _store, _pid, _tid = data_app
    assert snap_compare(app, press=("?", "_"), terminal_size=(100, 30))


def test_palette_screen(snap_compare, data_app) -> None:
    app, _store, pid, _tid = data_app

    async def run_before(pilot) -> None:
        from textual.widgets import Input, OptionList

        await pilot.pause()
        pilot.app.selected = ("plan", pid)
        pilot.app.push_screen(PaletteScreen(pilot.app._palette_context()))
        await pilot.pause()
        pilot.app.screen.query_one("#palette-input", Input).value = "theme"
        await pilot.pause()
        options = pilot.app.screen.query_one("#palette-list", OptionList)
        for index in range(options.option_count):
            if not options.get_option_at_index(index).disabled:
                options.highlighted = index
                break
        await pilot.pause()

    assert snap_compare(app, run_before=run_before, terminal_size=(100, 30))


def test_detail_read(snap_compare, data_app) -> None:
    app, store, _pid, tid = data_app

    async def run_before(pilot) -> None:
        await pilot.pause()
        pilot.app.push_screen(DetailScreen(store, "task", tid))
        await pilot.pause()

    assert snap_compare(app, run_before=run_before, terminal_size=(100, 30))


def test_source_empty(snap_compare, data_app) -> None:
    app, store, _pid, tid = data_app

    async def run_before(pilot) -> None:
        await pilot.pause()
        pilot.app.push_screen(SourceScreen(store, "task", tid))
        await pilot.pause(0.5)

    assert snap_compare(app, run_before=run_before, terminal_size=(100, 30))
