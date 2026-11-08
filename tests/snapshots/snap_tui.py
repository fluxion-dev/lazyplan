"""Deterministic SVG snapshots for the main TUI surfaces (pytest-only)."""

from __future__ import annotations

import os
import tempfile
import time
from contextlib import contextmanager
from unittest import mock

import pytest

from lazyplan import services
from lazyplan.core.entities import Status
from lazyplan.presentation.tui import create_app
from lazyplan.presentation.tui.screens import DetailScreen, PaletteScreen
from lazyplan.presentation.tui.screens.hub_kinds import CriteriaHub
from lazyplan.presentation.tui.screens.source import SourceScreen
from lazyplan.services import metrics, revisions
from lazyplan.store import Store

FIXED_START = 1_700_000_000.0
FIXED_NOW = FIXED_START + 30 * 86_400


@pytest.fixture(autouse=True)
def freeze_spinner(monkeypatch):
    """Keep doing-row frames deterministic across platforms."""
    monkeypatch.setenv("LAZYPLAN_NO_SPINNER", "1")


@contextmanager
def utc_timezone():
    """Pin local-time formatting so timeline labels match every runner."""
    previous = os.environ.get("TZ")
    os.environ["TZ"] = "UTC"
    if hasattr(time, "tzset"):
        time.tzset()
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous
        if hasattr(time, "tzset"):
            time.tzset()


@pytest.fixture()
def empty_app():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "empty.db")
        Store(db)
        yield create_app(db)


@pytest.fixture()
def data_app():
    real_snapshot = metrics.snapshot

    def frozen_snapshot(store, now=None, plan_id=None, scope_kind=None, scope_id=None):
        return real_snapshot(
            store,
            now=FIXED_NOW,
            plan_id=plan_id,
            scope_kind=scope_kind,
            scope_id=scope_id,
        )

    with utc_timezone(), tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "data.db")
        with mock.patch("lazyplan.store.base.time.time", return_value=FIXED_START):
            store = Store(db)
            plan = store.add_plan("Plan title", "What we build", goal="Why we build")
            milestone = store.add_milestone(plan.id, "Milestone title", "Milestone details")
            task = store.add_task(milestone.id, "Task title", "Task details")
            store.add_criteria("plan", plan.id, "The plan is readable")
            store.add_criteria("task", task.id, "The task is proven")
        store = Store(db)
        with mock.patch("lazyplan.services.metrics.snapshot", side_effect=frozen_snapshot):
            yield create_app(db), store, plan.id, task.id


def test_main_shell_empty(snap_compare, empty_app) -> None:
    assert snap_compare(empty_app, terminal_size=(120, 40))


@pytest.fixture()
def control_app():
    real_snapshot = metrics.snapshot

    def frozen_snapshot(store, now=None, plan_id=None, scope_kind=None, scope_id=None):
        return real_snapshot(
            store,
            now=FIXED_NOW,
            plan_id=plan_id,
            scope_kind=scope_kind,
            scope_id=scope_id,
        )

    with utc_timezone(), tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "control.db")
        with mock.patch("lazyplan.store.base.time.time", return_value=FIXED_START):
            store = Store(db)
            plan = store.add_plan("Control room", "What we build", goal="Why we build")
            milestone = store.add_milestone(plan.id, "See the work", "As a human, I triage.")
            blocked = store.add_task(milestone.id, "Blocked task", "Commit: one.")
            doing = store.add_task(milestone.id, "Review the flow", "Commit: one.")
            store.set_blocked(blocked.id, True, "waiting on design", actor="fixture")
            services.set_status(store, "task", doing.id, Status.DOING, actor="fixture")
            store.claim_task(doing.id, "Ada", 300)
            store.add_touchpoint(doing.id, "src/app", actor="fixture")
            store.add_question(plan.id, "Which host ships first?", actor="fixture")
            store.link_ref(
                plan.id,
                "https://example.com/epic",
                title="Epic",
                kind="epic",
                actor="fixture",
            )
            revisions.approve(store, plan.id, actor="fixture")
            store.update_task(doing.id, title="Review the flow (v2)", reason="scope change")
            ended, _ = store.start_session("Ada", plan_id=plan.id, branch="feat/control")
            store.end_session(
                ended.id,
                "Ada",
                summary="Closed the queue",
                handoff="next: review the overlap",
            )
            store.start_session("Ada", plan_id=plan.id, branch="feat/control-room")
        store = Store(db)
        with mock.patch("lazyplan.services.metrics.snapshot", side_effect=frozen_snapshot):
            yield create_app(db), plan.id


def test_control_room_shell(snap_compare, control_app) -> None:
    app, plan_id = control_app

    async def run_before(pilot) -> None:
        await pilot.pause()
        pilot.app.action_toggle_override()
        pilot.app.selected = ("plan", plan_id)
        pilot.app.update_preview(force=True)
        pilot.app.tree_controller.expand_all()
        await pilot.pause(0.2)

    with mock.patch("time.time", return_value=FIXED_NOW):
        assert snap_compare(app, run_before=run_before, terminal_size=(120, 40))


def test_criteria_hub_snapshot(snap_compare, control_app) -> None:
    app, plan_id = control_app

    async def run_before(pilot) -> None:
        await pilot.pause()
        app.push_screen(CriteriaHub(app.store, "plan", plan_id))
        await pilot.pause()

    assert snap_compare(app, run_before=run_before, terminal_size=(100, 30))


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
        palette_input = pilot.app.screen.query_one("#palette-input", Input)
        palette_input.cursor_blink = False
        palette_input.value = "theme"
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
