"""Deterministic SVG snapshots for the main TUI surfaces (pytest-only)."""

from __future__ import annotations

import os
import tempfile

import pytest

from lazyplan.store import Store
from lazyplan.tui import create_app
from lazyplan.tui.screens import DetailScreen, PaletteScreen
from lazyplan.tui.screens.source import SourceScreen


@pytest.fixture()
def empty_app():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "empty.db")
        Store(db)
        yield create_app(db)


@pytest.fixture()
def data_app():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "data.db")
        store = Store(db)
        plan = store.add_plan("Plan title", "What we build", goal="Why we build")
        milestone = store.add_milestone(plan.id, "Milestone title", "Milestone details")
        task = store.add_task(milestone.id, "Task title", "Task details")
        store.add_criteria("plan", plan.id, "The plan is readable")
        store.add_criteria("task", task.id, "The task is proven")
        store = Store(db)
        yield create_app(db), store, plan.id, task.id


def test_main_shell_empty(snap_compare, empty_app) -> None:
    assert snap_compare(empty_app, terminal_size=(120, 40))


def test_help_screen(snap_compare, data_app) -> None:
    app, _store, _pid, _tid = data_app
    assert snap_compare(app, press=("?", "_"), terminal_size=(100, 30))


def test_palette_screen(snap_compare, data_app) -> None:
    app, _store, pid, _tid = data_app

    async def run_before(pilot) -> None:
        await pilot.pause()
        pilot.app.selected = ("plan", pid)
        pilot.app.push_screen(PaletteScreen(pilot.app._palette_context()))
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
