#!/usr/bin/env python3
"""Capture every lpui screen and state for the UX review site.

Usage:
  .venv/bin/python tools/capture-ux-review.py [--out DIR] [--only ID ...]

Reuses the deterministic fixtures and SVG-to-PNG pipeline from
``capture-screens.py``. Every scene writes a PNG, a WebP, and one row in
``site/public/ux/scenes.json``; the review page reads that manifest directly.

Requires git, ImageMagick 7 with librsvg and WebP, and textual in the running
Python (use ``.venv/bin/python``).
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import io
import json
import os
import sys
import tempfile
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# Load the existing capture harness as a module so fixtures and image handling
# stay in one place. The filename has a dash, so importlib is required.
_spec = importlib.util.spec_from_file_location(
    "capture_screens", ROOT / "tools" / "capture-screens.py"
)
if _spec is None or _spec.loader is None:  # pragma: no cover - broken checkout
    raise SystemExit("error: cannot load tools/capture-screens.py")
cs = importlib.util.module_from_spec(_spec)
sys.modules["capture_screens"] = cs
_spec.loader.exec_module(cs)

from textual.widgets import Input, Tree  # noqa: E402

from lazyplan import services  # noqa: E402
from lazyplan.core.entities import Status  # noqa: E402
from lazyplan.infrastructure.environment import InstallInfo  # noqa: E402
from lazyplan.infrastructure.skills import AgentHost  # noqa: E402
from lazyplan.presentation.cli.parser import package_version  # noqa: E402
from lazyplan.presentation.tui import create_app  # noqa: E402
from lazyplan.presentation.tui.screens import (  # noqa: E402
    ConfirmScreen,
    FilterPromptScreen,
    HelpScreen,
    NewMilestoneScreen,
    NewPlanScreen,
    NewTaskScreen,
    PaletteScreen,
    PlanDiffScreen,
    RefScreen,
    SourceScreen,
    TextScreen,
    UpdateScreen,
)
from lazyplan.presentation.tui.screens.forms import CriterionScreen  # noqa: E402
from lazyplan.presentation.tui.screens.hub_coordination import (  # noqa: E402
    ClaimsHub,
    CommentsHub,
    SessionsHub,
)
from lazyplan.presentation.tui.screens.hub_kinds import (  # noqa: E402
    CriteriaHub,
    EvidenceHub,
    QuestionsHub,
    ReferencesHub,
)
from lazyplan.presentation.tui.screens.hub_provenance import (  # noqa: E402
    ActivityHub,
    PullRequestHub,
)
from lazyplan.store import Store  # noqa: E402

SIZE = cs.SIZE
TRANSCRIPT_SIZE = (120, 30)
DEFAULT_OUT = ROOT / "site" / "public" / "ux"
VERSION = package_version()


@dataclass(frozen=True)
class Scene:
    """One reviewable screen with the metadata the site displays."""

    id: str
    group: str
    title: str
    state: str
    description: str
    look_for: tuple[str, ...]
    keys: str
    build: Callable[[Path], Store | None]
    capture: Callable[[Store | None, Path], Any]
    size: tuple[int, int] = SIZE


def build_empty_fixture(tmp: Path) -> Store:
    """A fresh journal with no plans for the first-run empty state."""
    return Store(str(tmp / "plan.db"))


def attach_repo(store: Store, tmp: Path, task_id: int) -> None:
    """Create one deterministic checkout and link commits and PRs to a task."""
    repo = tmp / "web"
    repo.mkdir()
    cs.git(repo, "init", "-q", "-b", "main")
    cs.git(repo, "config", "user.email", cs.EMAIL)
    cs.git(repo, "config", "user.name", cs.AUTHOR)
    base = cs.commit(repo, "Add source trail scaffolding", cs.BASE_FILES)
    linked: list[tuple[str, str, tuple[str, ...]]] = []
    for subject, files in cs.COMMITS:
        linked.append((subject, cs.commit(repo, subject, files), tuple(files)))
    cs.git(repo, "remote", "add", "origin", cs.REMOTE)
    store.add_repo_link("task", task_id, str(repo), cs.REMOTE, branch="main", base_sha=base)
    for subject, sha, files in linked:
        store.link_commit(
            "task",
            task_id,
            sha,
            subject=subject,
            author=cs.AUTHOR,
            repo_root=str(repo),
            files=files,
        )
    for number, title, state, checks in cs.PRS:
        store.link_forge(
            "task",
            task_id,
            number,
            url=f"https://github.com/acme/web/pull/{number}",
            title=title,
            state=state,
            checks=checks,
        )


def build_search_fixture(tmp: Path) -> Store:
    """A small plan with enough rows to show text filtering and empty git."""
    store = Store(str(tmp / "plan.db"))
    plan = store.add_plan(
        "Search and bulk edit",
        "Find the row by what it says, then open it.",
        goal="Keep large journals navigable.",
    )
    milestone = store.add_milestone(plan.id, "Search workflow", "Text filters.")
    rows = (
        ("Find the release notes", "Search descriptions and notes."),
        ("Mark the queue rows", "Select several tasks."),
        ("Move the release set", "Apply one status change."),
        ("Release the stale leases", "Report conflicts per row."),
        ("Keep delete single-row", "Undo cannot recreate a subtree."),
    )
    for title, desc in rows:
        store.add_task(milestone.id, title, desc)
    with cs.mock.patch("lazyplan.store.base.time.time", return_value=cs.STAMP):
        services.set_status(store, "task", 1, Status.DOING, actor="Ada")
        services.set_status(store, "task", 2, Status.DOING, actor="Ada")
    store.add_note("task", 1, "Search covers descriptions, notes, and comments.", actor="Ada")
    return store


# -- rich fixture ---------------------------------------------------------


def build_ux_fixture(tmp: Path) -> Store:
    """The coordination journal plus proof, criteria, repos, and transcripts."""
    store = cs.build_control_room_fixture(tmp)
    plan = next(p for p in store.list_plans() if p.name == "Ship the coordination release")
    milestone = store.list_milestones(plan.id)[0]
    tasks = {task.title: task for task in store.list_tasks(milestone.id)}

    claimed = tasks["Claim the release queue (v2)"]
    aging = tasks["Review the flow health"]
    gap = tasks["Close with an open criterion"]

    store.add_touchpoint(claimed.id, "app/queue.py", actor="Ada")
    store.add_touchpoint(aging.id, "app/queue.py", actor="Ada")
    store.add_touchpoint(aging.id, "app/metrics.py", actor="Ada")
    store.claim_task(
        aging.id,
        "Lin",
        ttl_seconds=10 * 365 * 24 * 3600,
        note="Reviewing flow health",
    )

    c1 = store.add_criteria("plan", plan.id, "Claims never overlap silently", actor="Ada")
    c2 = store.add_criteria("plan", plan.id, "Every done task carries evidence", actor="Ada")
    store.add_criteria("plan", plan.id, "Attention fits in two lines", actor="Ada")
    store.add_criteria("milestone", milestone.id, "The queue slice is small enough to review")
    store.relate_criterion(c1.id, aging.id, actor="Ada")
    store.relate_criterion(c2.id, gap.id, actor="Ada")

    store.add_evidence(
        c1.id,
        command="pytest tests/test_coordination.py -q",
        exit_code=0,
        commit_sha="1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d",
        task_id=aging.id,
        note="overlap detection passes",
        actor="Ada",
    )
    store.add_evidence(
        c2.id,
        command="pytest tests/test_evidence.py -q",
        exit_code=0,
        task_id=gap.id,
        note="the earlier suite passed",
        actor="Ada",
    )
    store.add_evidence(
        c2.id,
        command="pytest tests/test_evidence.py -q",
        exit_code=1,
        task_id=gap.id,
        note="the open criterion still has no proof",
        actor="Ada",
    )

    task_criterion = store.add_criteria(
        "task", claimed.id, "The queue slice never overlaps another claim", actor="Ada"
    )
    store.relate_criterion(task_criterion.id, claimed.id, actor="Ada")
    store.add_evidence(
        task_criterion.id,
        command="pytest tests/test_claims.py -q",
        exit_code=0,
        commit_sha="a67b191e466e73f8cc9ba237b9a4cb2a3f3bcba2",
        task_id=claimed.id,
        note="overlap guard passes",
        actor="Ada",
    )
    store.add_criteria("task", claimed.id, "The handoff names the next slice", actor="Ada")

    second = store.add_question(plan.id, "Do claims survive a restart?", actor="Ada")
    services.resolve_question(store, second.id, actor="Ada", note="Yes, leases are persisted.")
    store.link_ref(
        plan.id,
        "https://linear.app/acme/issue/ENG-12",
        title="Coordination epic",
        kind="epic",
        actor="Ada",
    )
    store.link_ref(
        plan.id,
        "https://github.com/acme/web/issues/9",
        title="Design review notes",
        kind="doc",
        actor="Ada",
    )
    attach_repo(store, tmp, claimed.id)
    return store


# -- shell captures -------------------------------------------------------


def _row_node(tree: Tree[object], kind: str, oid: int) -> Any:
    for node in cs._nodes(tree, kind):
        if int(getattr(node, "data", {}).get("id", -1)) == oid:
            return node
    return None


async def _select_preserving(tree: Tree[object], node: Any, pilot: Any) -> None:
    """Select a row visually without Textual's select-toggles-expansion rule."""
    expanded = bool(getattr(node, "is_expanded", False))
    tree.select_node(node)
    await pilot.pause(0.12)
    if expanded and getattr(node, "allow_expand", False) and not node.is_expanded:
        node.expand()


async def _capture_shell(
    store: Store,
    target: Path,
    kind: str,
    oid: int,
    *,
    size: tuple[int, int] = SIZE,
    theme: str | None = None,
    timeline: bool = False,
    filter_text: str = "",
) -> None:
    patch = (
        cs.mock.patch.dict(os.environ, {"LAZYPLAN_THEME": theme})
        if theme is not None
        else cs.mock.patch.dict(os.environ, {}, clear=False)
    )
    with patch:
        app = create_app(str(store.path))
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            if filter_text:
                app.filter_text = filter_text
            app.refresh_all("")
            await pilot.pause(0.15)
            app.tree_controller.expand_all()
            await pilot.pause(0.1)
            tree = app.query_one("#tree", Tree)
            node = _row_node(tree, kind, oid)
            if node is not None:
                await _select_preserving(tree, node, pilot)
                tree.focus()
            if timeline:
                app.action_toggle_timeline()
            await pilot.pause(0.55)
            app.save_screenshot(str(target))


def _shell_scene(
    id: str,
    group: str,
    title: str,
    state: str,
    description: str,
    look_for: tuple[str, ...],
    keys: str,
    build: Callable[[Path], Store | None],
    kind: str,
    oid_of: Callable[[Store], int],
    **options: Any,
) -> Scene:
    async def capture(store: Store | None, target: Path) -> None:
        assert store is not None
        await _capture_shell(store, target, kind, oid_of(store), **options)

    return Scene(id, group, title, state, description, look_for, keys, build, capture)


def _plan_id(store: Store, name: str = "Ship the coordination release") -> int:
    return next(plan.id for plan in store.list_plans() if plan.name == name)


def _milestone_id(store: Store) -> int:
    return store.list_milestones(_plan_id(store))[0].id


def _task_id(store: Store, title: str) -> int:
    return cs._task_id(store, title)


# -- hub captures ---------------------------------------------------------


async def _capture_hub(store: Store, target: Path, screen: Any) -> None:
    app = create_app(str(store.path))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        app.push_screen(screen)
        await pilot.pause(0.5)
        app.save_screenshot(str(target))


def _activity_hub(store: Store) -> ActivityHub:
    """Activity rows from the human actor, without fixture checkout paths."""
    hub = ActivityHub(store)
    hub.actor_filter = "Ada"
    return hub


def _hub_scene(
    id: str,
    group: str,
    title: str,
    state: str,
    description: str,
    look_for: tuple[str, ...],
    keys: str,
    build: Callable[[Path], Store | None],
    make: Callable[[Store], Any],
) -> Scene:
    async def capture(store: Store | None, target: Path) -> None:
        assert store is not None
        await _capture_hub(store, target, make(store))

    return Scene(id, group, title, state, description, look_for, keys, build, capture)


# -- modal captures -------------------------------------------------------


async def _capture_modal(store: Store, target: Path, screen: Any) -> None:
    app = create_app(str(store.path))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        app.push_screen(screen)
        await pilot.pause(0.45)
        app.save_screenshot(str(target))


def _modal_scene(
    id: str,
    title: str,
    state: str,
    description: str,
    look_for: tuple[str, ...],
    keys: str,
    build: Callable[[Path], Store | None],
    make: Callable[[Store], Any],
) -> Scene:
    async def capture(store: Store | None, target: Path) -> None:
        assert store is not None
        await _capture_modal(store, target, make(store))

    return Scene(id, "forms", title, state, description, look_for, keys, build, capture)


# -- source captures ------------------------------------------------------


async def _capture_source(
    store: Store,
    target: Path,
    task_title: str,
    pick: str,
    size: tuple[int, int] = SIZE,
) -> None:
    task_id = _task_id(store, task_title)
    app = create_app(str(store.path))
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        app.push_screen(SourceScreen(store, "task", task_id))
        await pilot.pause(0.45)
        tree = app.screen.query_one("#source-tree", Tree)
        repo = tree.root.children[0]
        repo.expand()
        commit = next(
            (
                child
                for child in repo.children
                if child.data.get("kind") == "commit" and "Render diffs" in str(child.label)
            ),
            repo.children[0],
        )
        commit.expand()
        for _ in range(20):
            if any("M " in str(child.label) for child in commit.children):
                break
            await pilot.pause(0.05)
        tree.focus()
        node = commit.children[0] if pick in ("file", "split") else commit
        await _select_preserving(tree, node, pilot)
        app.screen._preview(node)
        if pick == "split":
            app.screen.action_toggle_split()
        await pilot.pause(0.5)
        app.save_screenshot(str(target))


def _source_scene(
    id: str,
    title: str,
    state: str,
    description: str,
    look_for: tuple[str, ...],
    keys: str,
    build: Callable[[Path], Store | None],
    task_title: str,
    pick: str,
    size: tuple[int, int] = SIZE,
) -> Scene:
    async def capture(store: Store | None, target: Path) -> None:
        assert store is not None
        await _capture_source(store, target, task_title, pick, size)

    return Scene(
        id,
        "source",
        title,
        state,
        description,
        look_for,
        keys,
        build,
        capture,
        size,
    )


# -- transcript captures --------------------------------------------------


class TranscriptApp(cs.TranscriptApp):
    """A larger dark terminal surface for CLI and setup output."""


async def _capture_transcript(
    store: Store | None,
    target: Path,
    text: str,
    title: str,
    size: tuple[int, int] = TRANSCRIPT_SIZE,
) -> None:
    from rich.text import Text

    body = Text.from_ansi(text) if "\x1b[" in text else Text(text)
    app = TranscriptApp(body, title)
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        app.save_screenshot(str(target))


def _transcript_scene(
    id: str,
    title: str,
    state: str,
    description: str,
    look_for: tuple[str, ...],
    keys: str,
    text: Callable[[Store], str],
    build: Callable[[Path], Store | None],
    size: tuple[int, int] = TRANSCRIPT_SIZE,
) -> Scene:
    async def capture(store: Store | None, target: Path) -> None:
        assert store is not None
        await _capture_transcript(store, target, text(store), title, size)

    return Scene(id, "cli", title, state, description, look_for, keys, build, capture, size)


def _cli_text(store: Store, *args: str) -> str:
    """Run one real CLI invocation against the fixture and return its output."""
    from lazyplan.presentation.cli import main

    out = io.StringIO()
    err = io.StringIO()
    argv = ["--db", str(store.path), *args]
    try:
        with redirect_stdout(out), redirect_stderr(err):
            main(argv)
    except SystemExit:
        pass
    text = out.getvalue()
    if err.getvalue():
        text += "\n" + err.getvalue()
    return text.rstrip() + "\n"


# -- scenes ---------------------------------------------------------------


def scenes() -> list[Scene]:
    ux = build_ux_fixture
    source = cs.build_source_fixture
    empty = build_empty_fixture
    out: list[Scene] = []

    out.extend(
        [
            Scene(
                "shell-empty",
                "shell",
                "Empty journal",
                "No plans yet",
                "The first-run shell with no plans: the tree, preview, agents, and git panes each explain the next action.",
                (
                    "Do the three empty panes read as one instruction or three competing ones?",
                    "Is the create hint obvious at the width you use?",
                    "Does the status line earn its space?",
                ),
                "n new · ? help · c commands",
                empty,
                lambda store, target: _capture_shell(store, target, "plan", 0),
            ),
            _shell_scene(
                "shell-plan",
                "shell",
                "Plan overview",
                "Plan selected",
                "The plan overview: health strip, why and what, approval drift, an open question, references, milestones, acceptance, and the next tasks.",
                (
                    "Scan order from health, to scope, to milestones.",
                    "Whether the approval drift line is understandable without the diff.",
                    "How much of the preview is visible before scrolling.",
                ),
                "j/k select · s status · e edit · c commands",
                ux,
                kind="plan",
                oid_of=lambda store: _plan_id(store),
            ),
            _shell_scene(
                "shell-milestone",
                "shell",
                "Milestone overview",
                "Milestone selected",
                "A milestone selection: slice health, the milestone description, its tasks with claims and blocks, acceptance, and linked source.",
                (
                    "Does the milestone feel like a slice rather than a folder?",
                    "Are task claims and blocks readable at a glance?",
                    "Is the breadcrumb enough to know where you are?",
                ),
                "j/k select · z fold · s status",
                ux,
                kind="milestone",
                oid_of=lambda store: _milestone_id(store),
            ),
            _shell_scene(
                "shell-task",
                "shell",
                "Task overview",
                "Task selected with linked source",
                "A task selection: work health, claim, proof rows, notes, acceptance, and the GIT pane with checkout, commits, and pull requests.",
                (
                    "Does the title-only row keep the tree scannable while the overview carries claim and proof?",
                    "Does the GIT pane compete with the task body?",
                    "Is the proof section scannable when there are several criteria?",
                ),
                "g source · k claims · m comments · P pull requests",
                ux,
                kind="task",
                oid_of=lambda store: _task_id(store, "Claim the release queue (v2)"),
            ),
            _shell_scene(
                "shell-attention",
                "shell",
                "Attention and control strip",
                "Attention markers, aging, gaps, red checks",
                "The plan tree with title-only task rows and attention markers on a blocked task, aging work, a done row with an open criterion, and a failing pull-request check.",
                (
                    "Does the control strip name the reasons to intervene?",
                    "Are the glyphs and row colors distinguishable?",
                    "Does the health line match the rows below it?",
                ),
                "j/k select · space mark · c commands",
                ux,
                kind="plan",
                oid_of=lambda store: _plan_id(store),
            ),
            _shell_scene(
                "shell-filter",
                "shell",
                "Filtered tree",
                "Text filter applied",
                "The tree filtered by text. Matching branches stay open, so the hits and their sibling context are both visible.",
                (
                    "Can you tell a filter is active without reading the status line?",
                    "Does showing full matching branches make the tree look unfiltered?",
                    "Should the filter be a prompt, an inline field, or both?",
                ),
                "/ filter · escape clear",
                build_search_fixture,
                kind="task",
                oid_of=lambda store: 2,
                filter_text="queue",
            ),
            _shell_scene(
                "shell-narrow",
                "shell",
                "Narrow terminal",
                "Stacked layout at 78 columns",
                "The shell at 78 columns: the overview hides, and the plan queue, plan review, agents, and git cards stack vertically.",
                (
                    "Is the compact layout still legible?",
                    "What information disappears first, and is that the right order?",
                    "Do wrapped rows lose their status glyphs?",
                ),
                "resize the terminal · ? help",
                ux,
                kind="task",
                oid_of=lambda store: _task_id(store, "Claim the release queue (v2)"),
                size=(78, 24),
            ),
            _shell_scene(
                "shell-wide",
                "shell",
                "Wide terminal",
                "Wide layout with timeline",
                "The shell at 170 columns with the timeline visible, showing how the side panes and the bottom timeline share the extra space.",
                (
                    "Does the wide layout use the space intentionally?",
                    "Should the timeline be always-on or opt-in at this width?",
                    "Is the preview line length comfortable?",
                ),
                "T timeline · t theme",
                cs.build_timeline_fixture,
                kind="milestone",
                oid_of=lambda store: store.list_milestones(store.list_plans()[0].id)[0].id,
                size=(170, 45),
                timeline=True,
            ),
            _shell_scene(
                "shell-timeline",
                "shell",
                "Timeline",
                "Milestone-scoped timeline",
                "The timeline card with a milestone selected, keeping the milestone lane and its tasks while the rest of the plan stays quiet.",
                (
                    "Is the lane grammar readable without a legend?",
                    "Are start positions and missing lanes understandable?",
                    "Does the card crowd the tree at normal height?",
                ),
                "T show/hide timeline",
                cs.build_timeline_fixture,
                kind="milestone",
                oid_of=lambda store: store.list_milestones(store.list_plans()[0].id)[0].id,
                timeline=True,
            ),
            _shell_scene(
                "shell-theme-void",
                "shell",
                "Theme: void",
                "OLED-black theme",
                "The shell in the void theme, the high-contrast black palette for dark rooms.",
                (
                    "Are the accent colors still distinguishable?",
                    "Does the border contrast hold up?",
                    "Is the selected row obvious without color alone?",
                ),
                "t cycle theme",
                source,
                kind="task",
                oid_of=lambda store: _task_id(store, "Render unified diffs"),
                theme="void",
            ),
            _shell_scene(
                "shell-theme-latte",
                "shell",
                "Theme: latte",
                "Light theme",
                "The shell in the latte theme, the light palette for bright rooms and screen sharing.",
                (
                    "Does the light theme keep status colors legible?",
                    "Are borders and dim text still readable?",
                    "Is the diff and code text comfortable on light backgrounds?",
                ),
                "t cycle theme",
                source,
                kind="task",
                oid_of=lambda store: _task_id(store, "Render unified diffs"),
                theme="latte",
            ),
            _shell_scene(
                "shell-task-unlinked",
                "shell",
                "Task without source",
                "No repo or commits linked",
                "A task selection with no linked repository: the GIT pane explains the next action instead of going blank.",
                (
                    "Is the empty GIT pane useful or just noise?",
                    "Should an unlinked task hide the pane entirely?",
                    "Does the preview still explain why source is missing?",
                ),
                "g source · c commands",
                build_search_fixture,
                kind="task",
                oid_of=lambda store: 1,
            ),
        ]
    )

    out.extend(
        [
            _hub_scene(
                "hub-criteria",
                "trust",
                "Criteria hub",
                "Plan criteria with evidence states",
                "The criteria hub for a plan: checklist rows, proof state, and a preview that names evidence and proving tasks.",
                (
                    "Is done/open mixed with pass/fail readable?",
                    "Does the preview explain what evidence exists?",
                    "Are the hub action hints discoverable?",
                ),
                "a add · e edit · p prove · l relate · d delete",
                ux,
                lambda store: CriteriaHub(store, "plan", _plan_id(store)),
            ),
            _hub_scene(
                "hub-evidence",
                "trust",
                "Evidence hub",
                "Criterion with pass and fail rows",
                "The evidence hub for one criterion, with command, exit code, commit, task, and note for each proof row.",
                (
                    "Can you tell which row is the latest and whether it passes?",
                    "Is the command the most important field?",
                    "Does the list need grouping or a verdict column?",
                ),
                "p prove · o open · y copy",
                ux,
                lambda store: EvidenceHub(
                    store,
                    next(
                        criterion.id
                        for criterion in store.list_criteria("plan", _plan_id(store))
                        if criterion.text.startswith("Every done")
                    ),
                    context="plan #1",
                ),
            ),
            _hub_scene(
                "hub-questions",
                "trust",
                "Questions hub",
                "Open and resolved plan questions",
                "The questions hub: open questions that block readiness, a resolved question with its resolution, and the readiness note in the preview.",
                (
                    "Is the effect on readiness obvious?",
                    "Can you tell resolve from reopen?",
                    "Does the preview repeat the row too much?",
                ),
                "a add · x toggle · esc back",
                ux,
                lambda store: QuestionsHub(store, _plan_id(store)),
            ),
            _hub_scene(
                "hub-references",
                "trust",
                "References hub",
                "External epic and doc links",
                "The references hub: read-only external links with provider, kind, title, and URL.",
                (
                    "Is the read-only nature of references clear?",
                    "Is the provider visible enough to trust the link?",
                    "Does open versus unlink need more separation?",
                ),
                "a link · o open · d unlink",
                ux,
                lambda store: ReferencesHub(store, _plan_id(store)),
            ),
            _hub_scene(
                "hub-claims",
                "coordination",
                "Claims and touch-points hub",
                "Active claim, overlap, and touch-points",
                "The claims hub for one task: holder, expiry, age, note, one overlapping lease, and the touch-point list.",
                (
                    "Can you see why a claim is risky?",
                    "Are renew, release, and force release distinguishable?",
                    "Does the expiry date need a relative time too?",
                ),
                "a claim · x renew · d release · D force",
                ux,
                lambda store: ClaimsHub(
                    store,
                    task_id=_task_id(store, "Claim the release queue (v2)"),
                    plan_id=_plan_id(store),
                ),
            ),
            _hub_scene(
                "hub-sessions",
                "coordination",
                "Sessions and handoffs hub",
                "Active and ended sessions",
                "The sessions hub: actor, host, branch, age, idle time, summary, handoff, and the recent event trail.",
                (
                    "Can you tell which agent needs you?",
                    "Is idle time more useful than start time?",
                    "Is the handoff easy to find?",
                ),
                "a start · d end · x end",
                ux,
                lambda store: SessionsHub(store, _plan_id(store)),
            ),
            _hub_scene(
                "hub-comments",
                "coordination",
                "Comments and notes hub",
                "Open comments and a handoff note",
                "The comments hub: review comments, a handoff note, and the unresolved-only filter.",
                (
                    "Are comments and notes visually distinct?",
                    "Is the unresolved filter discoverable?",
                    "Can you tell who wrote what?",
                ),
                "a comment · n note · e edit · x resolve · u filter",
                ux,
                lambda store: CommentsHub(
                    store, "task", _task_id(store, "Claim the release queue (v2)")
                ),
            ),
            _hub_scene(
                "hub-pull-requests",
                "provenance",
                "Pull request hub",
                "Cached PR with failing checks",
                "The pull request hub: cached state, base and head refs, checks, reviews, merge time, URL, and the refresh boundary.",
                (
                    "Is stale data marked clearly?",
                    "Does the user know refresh is the only network action?",
                    "Are checks and reviews scannable at a glance?",
                ),
                "a link · r refresh · d unlink · o open",
                ux,
                lambda store: PullRequestHub(
                    store, "task", _task_id(store, "Gate on the red checks")
                ),
            ),
            _hub_scene(
                "hub-activity",
                "provenance",
                "Activity hub",
                "Recent feed with jump targets",
                "The activity hub: actor, event, detail, and the row each event can jump back to.",
                (
                    "Can you reconstruct what changed without timestamps?",
                    "Is the actor filter visible enough?",
                    "Does every row need a jump target?",
                ),
                "f actor · K kind · enter jump",
                ux,
                _activity_hub,
            ),
        ]
    )

    out.extend(
        [
            _source_scene(
                "source-commit",
                "Commit selected",
                "Commit diff preview",
                "The source trail with a commit selected: repository, author, changed files, and a unified diff beside the tree.",
                (
                    "Is the tree-to-diff relationship obvious?",
                    "Does the diff need syntax color to be useful?",
                    "Are commit metadata and files in the right order?",
                ),
                "enter owner · o open · y copy · / filter",
                source,
                "Render unified diffs",
                "commit",
            ),
            _source_scene(
                "source-file",
                "File selected",
                "File diff preview",
                "The source trail with one changed file selected: path, status, and the line-level diff.",
                (
                    "Can you tell which file and commit you are looking at?",
                    "Is the file hierarchy clear in the tree?",
                    "Should the diff own more of the screen?",
                ),
                "enter owner · o open · y copy",
                source,
                "Render unified diffs",
                "file",
            ),
            _source_scene(
                "source-split",
                "Side-by-side diff",
                "Split diff",
                "One file paired old and new, with status, counts, word-level emphasis, and wrapped lines.",
                (
                    "Do paired rows read faster than the unified view?",
                    "Is the separator obvious at this width?",
                    "When should split turn itself off?",
                ),
                "s unified · w wrap · f fold · n/p file",
                source,
                "Render unified diffs",
                "split",
                (170, 40),
            ),
            Scene(
                "source-empty",
                "source",
                "Source trail with no links",
                "No source linked",
                "The source trail for a task with no linked checkout, commits, or pull requests.",
                (
                    "Does the empty state name the exact command to fix it?",
                    "Should the screen be reachable at all when there is no source?",
                    "Is the header summary useful when everything is zero?",
                ),
                "g source · esc back",
                ux,
                lambda store, target: _capture_empty_source(store, target),
            ),
            Scene(
                "source-filter",
                "source",
                "Source filter",
                "Filter field open",
                "The source trail with the filter field open, matching commits, files, and pull requests.",
                (
                    "Is the filter field clearly temporary?",
                    "Does the tree show why rows disappeared?",
                    "Should filter and search be the same gesture as the tree?",
                ),
                "/ filter · enter apply · esc hidden",
                source,
                lambda store, target: _capture_source_filter(store, target),
            ),
        ]
    )

    out.extend(
        [
            _modal_scene(
                "form-new-plan",
                "New plan",
                "Create form with three fields",
                "The create-plan form: title, why, and what, with multiline fields for the definition.",
                (
                    "Does the form teach what a plan needs?",
                    "Are why and what too open-ended?",
                    "Is the primary action obvious?",
                ),
                "tab next · enter submit · esc cancel",
                ux,
                lambda store: NewPlanScreen(),
            ),
            _modal_scene(
                "form-new-milestone",
                "New milestone",
                "Create form scoped to a plan",
                "The create-milestone form for one plan, with a title and a details field.",
                (
                    "Does the context line tell you which plan you are adding to?",
                    "Is the difference between a milestone and a task clear?",
                    "Does the placeholder ask for user value?",
                ),
                "tab next · enter submit · esc cancel",
                ux,
                lambda store: NewMilestoneScreen(_plan_id(store), context=f"P{_plan_id(store)}"),
            ),
            _modal_scene(
                "form-new-task",
                "New task",
                "Create form scoped to a milestone",
                "The create-task form for one milestone, with a title and a details field.",
                (
                    "Does the details placeholder ask for approach and verification?",
                    "Is the parent milestone obvious?",
                    "Should the form suggest a commit slice?",
                ),
                "tab next · enter submit · esc cancel",
                ux,
                lambda store: NewTaskScreen(
                    _milestone_id(store), context=f"M{_milestone_id(store)}"
                ),
            ),
            _modal_scene(
                "form-edit-task",
                "Edit task",
                "Edit form prefilled",
                "The edit-task form with existing text filled in, showing the edit variant of the create form.",
                (
                    "Does the title switch from New to Edit clearly?",
                    "Are long descriptions comfortable in the text area?",
                    "Is Save distinct from Cancel?",
                ),
                "tab next · enter save · esc cancel",
                ux,
                lambda store: NewTaskScreen(
                    _milestone_id(store),
                    defaults={
                        "title": "Claim the release queue (v2)",
                        "desc": "Lease the queue slice.\n\nCommit: queue slice.\n\nVerify: claims never overlap.",
                    },
                    context=f"M{_milestone_id(store)}",
                    editing=True,
                ),
            ),
            _modal_scene(
                "form-add-criterion",
                "Add criterion",
                "Criterion form with context",
                "The add-criterion form opened from a task selection, with a text field and a done checkbox.",
                (
                    "Does the dialog read as adding rather than editing?",
                    "Is the done checkbox useful before the criterion exists?",
                    "Does the wider text field fit a full criterion?",
                ),
                "tab next · enter add · esc cancel",
                ux,
                lambda store: CriterionScreen(creating=True),
            ),
            _modal_scene(
                "form-edit-criterion",
                "Edit criterion",
                "Text and completion in one dialog",
                "The edit-criterion form with the criterion text and a done checkbox.",
                (
                    "Is the done checkbox the right control?",
                    "Should proof be visible while editing?",
                    "Is the dialog title enough context?",
                ),
                "tab next · enter submit · esc cancel",
                ux,
                lambda store: CriterionScreen("Attention fits in two lines", done=False),
            ),
            _modal_scene(
                "form-link-reference",
                "Link reference",
                "URL, type, and optional title",
                "The external reference form: URL, kind, and a short title.",
                (
                    "Is the type field understandable?",
                    "Should the app infer the provider from the URL?",
                    "Is a read-only reference clearly not a sync?",
                ),
                "tab next · enter link · esc cancel",
                ux,
                lambda store: RefScreen(),
            ),
            _modal_scene(
                "form-confirm-delete",
                "Confirm delete",
                "Destructive confirmation",
                "The first delete confirmation, with the parent and child warning.",
                (
                    "Is the safe choice focused by default?",
                    "Does the copy say what else disappears?",
                    "Is a second reason prompt too much friction?",
                ),
                "tab choose · enter confirm · esc cancel",
                ux,
                lambda store: ConfirmScreen("Delete task #3?\n(children go too.)"),
            ),
            _modal_scene(
                "form-delete-reason",
                "Delete reason",
                "Second step after confirm",
                "The required reason prompt after the destructive confirmation.",
                (
                    "Does the two-step delete feel safer or slower?",
                    "Is the reason field required at the right moment?",
                    "Should the reason be visible in the feed?",
                ),
                "enter delete · esc cancel",
                ux,
                lambda store: FilterPromptScreen(
                    "Delete task #3? Why?", "reason for deleting…", "Delete"
                ),
            ),
            _modal_scene(
                "form-filter",
                "Filter tree",
                "One-line filter prompt",
                "The tree text filter prompt, with an empty value clearing the filter.",
                (
                    "Does the prompt explain that empty clears?",
                    "Should filtering be inline in the tree?",
                    "Is the scope (whole tree) obvious?",
                ),
                "enter apply · esc cancel",
                ux,
                lambda store: FilterPromptScreen(),
            ),
            _modal_scene(
                "form-approve",
                "Approve plan",
                "Reason required after drift",
                "The approval prompt that records why a scope is approved after drift.",
                (
                    "Does the FILTER heading fit an approval prompt?",
                    "Does the title explain why a reason is required after drift?",
                    "Should the diff be shown before this prompt?",
                ),
                "enter approve · esc cancel",
                ux,
                lambda store: FilterPromptScreen(
                    f"Approve P{_plan_id(store)}? Why? (required after drift)",
                    "why this scope is approved…",
                    "Approve",
                ),
            ),
            _modal_scene(
                "form-start-session",
                "Start session",
                "Optional branch input",
                "The start-session prompt with an optional branch.",
                (
                    "Is it clear that the branch is optional?",
                    "Does starting a session need a plan context line?",
                    "Who is the actor, and should the form say?",
                ),
                "enter start · esc cancel",
                ux,
                lambda store: FilterPromptScreen("Start session", "branch (optional)", "Start"),
            ),
            _modal_scene(
                "form-add-comment",
                "Add comment",
                "Review comment prompt",
                "The add-comment prompt attached to one task.",
                (
                    "Is the parent row named?",
                    "Does comment versus note need an explanation?",
                    "Is @mention support discoverable?",
                ),
                "enter add · esc cancel",
                ux,
                lambda store: FilterPromptScreen("Add comment", "review comment", "Add"),
            ),
            _modal_scene(
                "form-add-note",
                "Add note",
                "Handoff note prompt",
                "The add-note prompt for a handoff or decision.",
                (
                    "Is note versus comment clear?",
                    "Does the placeholder imply permanence?",
                    "Should notes be immutable?",
                ),
                "enter add · esc cancel",
                ux,
                lambda store: FilterPromptScreen("Add note", "handoff note", "Add"),
            ),
            _modal_scene(
                "form-link-pr",
                "Link pull request",
                "GitHub URL prompt",
                "The prompt to attach a pull request URL to the selected row.",
                (
                    "Does the placeholder show the expected URL shape?",
                    "Is an invalid URL handled clearly?",
                    "Should linking be possible without a URL?",
                ),
                "enter link · esc cancel",
                ux,
                lambda store: FilterPromptScreen(
                    "Link pull request", "https://github.com/…/pull/N", "Link"
                ),
            ),
            _modal_scene(
                "form-filter-actor",
                "Filter activity by actor",
                "Filter prompt with blank meaning all",
                "The activity hub actor filter, where blank input clears the filter.",
                (
                    "Is blank-for-all clear?",
                    "Should actor filters be a picker?",
                    "Is the filter state visible after applying?",
                ),
                "enter filter · esc cancel",
                ux,
                lambda store: FilterPromptScreen(
                    "Filter actor", "actor name (blank for all)", "Filter"
                ),
            ),
            Scene(
                "form-export",
                "forms",
                "Export plan",
                "Folder tree and filename",
                "The Markdown export picker: destination path, folder tree, filename, error line, and actions.",
                (
                    "Is the destination editable and clear?",
                    "Does the folder tree earn the space?",
                    "Is overwrite protection visible before you press Export?",
                ),
                "tab move · enter export · esc cancel",
                cs.build_export_fixture,
                _capture_export,
            ),
            _modal_scene(
                "form-export-overwrite",
                "Overwrite export",
                "Destructive confirmation",
                "The overwrite confirmation that appears when the chosen export path already exists.",
                (
                    "Is the full target path shown?",
                    "Is overwrite styled as dangerous enough?",
                    "Could the picker prevent this earlier?",
                ),
                "tab choose · enter overwrite · esc cancel",
                cs.build_export_fixture,
                lambda store: ConfirmScreen(
                    "Overwrite ~/Downloads/plan-P1.md?",
                    confirm_label="Overwrite",
                    variant="warning",
                ),
            ),
            _modal_scene(
                "form-update",
                "Update lpui",
                "Installed versus latest",
                "The update screen with an installed and a newer version, plus the download action.",
                (
                    "Does the screen explain when the update applies?",
                    "Is the install method relevant to the user?",
                    "Is Later the easy exit?",
                ),
                "enter download · esc close",
                ux,
                lambda store: UpdateScreen(
                    "0.35.0", "0.36.0", InstallInfo(method="pip", upgradeable=True)
                ),
            ),
            Scene(
                "form-plan-diff",
                "source",
                "Plan scope diff",
                "Drifted plan",
                "The dedicated plan diff: summary chips, sections by kind, before and after blocks, and the reason for each change.",
                (
                    "Is the summary enough to decide whether to approve?",
                    "Do the before and after blocks read as one change?",
                    "Are reasons visible without crowding the rows?",
                ),
                "esc back · q quit",
                ux,
                _capture_plan_diff,
            ),
            _modal_scene(
                "overlay-help",
                "Help",
                "Task-grouped key reference",
                "The help overlay shared by `?`, `lpui help`, and every screen.",
                (
                    "Is the OBSERVE/WRITE split useful?",
                    "Are the groups in the right order?",
                    "Does the key column scan well?",
                ),
                "esc close · c commands",
                ux,
                lambda store: HelpScreen(),
            ),
            _modal_scene(
                "overlay-palette",
                "Command palette",
                "All commands grouped by mode",
                "The command palette with every command, section headers, key hints, and disabled context.",
                (
                    "Can you find a command by intent?",
                    "Do section headers help or add noise?",
                    "Is the mode split visible enough?",
                ),
                "type search · enter run · esc cancel",
                ux,
                lambda store: PaletteScreen({}),
            ),
            Scene(
                "overlay-palette-filtered",
                "forms",
                "Filtered command palette",
                "Search narrows the list",
                "The palette after typing a query, with the result count and the first runnable command highlighted.",
                (
                    "Does the count help?",
                    "Are matching aliases visible?",
                    "Is the disabled context explained?",
                ),
                "type search · enter run · esc cancel",
                ux,
                _capture_palette_filtered,
            ),
        ]
    )

    out.extend(
        [
            _transcript_scene(
                "cli-help",
                "CLI help",
                "`lpui help`",
                "The task-grouped help at the shell, the same source as the `?` overlay.",
                (
                    "Does the shell help match the overlay?",
                    "Is the key column aligned?",
                    "Are deprecated keys visible but quiet?",
                ),
                "lpui help",
                lambda store: _cli_text(store, "help"),
                ux,
            ),
            _transcript_scene(
                "cli-list",
                "CLI list",
                "`lpui list --tree`",
                "The plan tree with status glyphs, progress, and the agent-facing view.",
                (
                    "Is the tree scannable in a terminal transcript?",
                    "Do the glyphs survive a monochrome terminal?",
                    "Is progress easy to compare across rows?",
                ),
                "lpui list --tree",
                lambda store: _cli_text(store, "list", "--tree"),
                ux,
            ),
            _transcript_scene(
                "cli-show",
                "CLI show",
                "`lpui show --kind plan`",
                "One plan's why, what, criteria, and children in the shell.",
                (
                    "Does the show output match the overview?",
                    "Is the hierarchy clear without color?",
                    "Is the output too long for one screen?",
                ),
                "lpui show --kind plan --id 1",
                lambda store: _cli_text(
                    store, "show", "--kind", "plan", "--id", str(_plan_id(store))
                ),
                ux,
            ),
            _transcript_scene(
                "cli-stats",
                "CLI stats",
                "`lpui stats --since 400.days`",
                "Flow health at the shell: WIP, cycle time, throughput, aging, stale work, reopened work, claims, and blocked tasks.",
                (
                    "Is the metric vocabulary explained?",
                    "Which numbers need a sparkline or trend?",
                    "Does this belong in the TUI?",
                ),
                "lpui stats --since 400.days",
                lambda store: _cli_text(store, "stats", "--since", "400.days"),
                ux,
            ),
            _transcript_scene(
                "cli-review",
                "CLI review",
                "`lpui review --plan 1`",
                "The deterministic review packet handed to an agent.",
                (
                    "Does the packet read like a handoff?",
                    "Is the order right for a reviewer?",
                    "Does it duplicate the show output too much?",
                ),
                "lpui review --plan 1",
                lambda store: _cli_text(store, "review", "--plan", str(_plan_id(store))),
                ux,
            ),
            _transcript_scene(
                "cli-feed",
                "CLI feed",
                "`lpui feed --limit 12`",
                "The activity feed at the shell, with actor and event detail.",
                (
                    "Can you reconstruct a session from the feed?",
                    "Is actor noise or signal?",
                    "Should the feed group related events?",
                ),
                "lpui feed --limit 12",
                lambda store: _cli_text(store, "feed", "--limit", "12"),
                ux,
            ),
            Scene(
                "setup-wizard",
                "cli",
                "Setup wizard",
                "Placement, agents, and review",
                "The first-run setup wizard: where plans live, which agents get the skill, and the review of everything installation will write.",
                (
                    "Does the wizard explain the placement tradeoff?",
                    "Are detected agents obvious?",
                    "Is the review step scannable before writing?",
                ),
                "lpui setup",
                ux,
                _capture_setup,
            ),
        ]
    )
    # Keep a stable, human-readable order inside each group.
    return out


# -- bespoke captures -----------------------------------------------------


async def _capture_empty_source(store: Store, target: Path) -> None:
    task_id = _task_id(store, "Wait on the infra window")
    app = create_app(str(store.path))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        app.push_screen(SourceScreen(store, "task", task_id))
        await pilot.pause(0.6)
        app.save_screenshot(str(target))


async def _capture_source_filter(store: Store, target: Path) -> None:
    task_id = _task_id(store, "Render unified diffs")
    app = create_app(str(store.path))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        app.push_screen(SourceScreen(store, "task", task_id))
        await pilot.pause(0.5)
        screen = app.screen
        screen.action_filter()
        field = screen.query_one("#source-filter", Input)
        field.value = "diff"
        await pilot.pause(0.45)
        tree = screen.query_one("#source-tree", Tree)
        repo = tree.root.children[0]
        commit = repo.children[0]
        commit.expand()
        node = commit.children[0]
        tree.select_node(node)
        screen._preview(node)
        await pilot.pause(0.5)
        app.save_screenshot(str(target))


async def _capture_export(store: Store, target: Path) -> None:
    await cs.capture_export(store, target)


async def _capture_plan_diff(store: Store, target: Path) -> None:
    """Approve the fixture, add drift, and capture the dedicated diff screen."""
    plan_id = _plan_id(store)
    plan = store.get_plan(plan_id)
    if plan is None:
        return
    if not store.list_revisions(plan_id):
        services.approve(store, plan_id, actor="fixture", reason="baseline")
    store.update_plan(
        plan_id,
        description=(plan.description or "") + "\n\nScope added for the review.",
        actor="fixture",
    )
    result = services.diff(store, plan_id)
    app = create_app(str(store.path))
    async with app.run_test(size=(120, 30)) as pilot:
        app.push_screen(PlanDiffScreen(result))
        await pilot.pause()
        app.save_screenshot(str(target))


async def _capture_palette_filtered(store: Store, target: Path) -> None:
    app = create_app(str(store.path))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        app.push_screen(PaletteScreen({}))
        await pilot.pause()
        app.screen.query_one("#palette-input", Input).value = "hub"
        await pilot.pause(0.5)
        app.save_screenshot(str(target))


async def _capture_setup(store: Store, target: Path) -> None:
    from lazyplan.presentation.setup import ui

    hosts = [
        AgentHost("opencode", "OpenCode", True, "~/.config/opencode/skills"),
        AgentHost("claude", "Claude Code", True, "~/.claude/skills"),
        AgentHost("codex", "Codex", False, "not detected"),
        AgentHost("cursor", "Cursor", False, "not detected"),
    ]
    buf = io.StringIO()

    def answer(text: str) -> Callable[[], str]:
        def read() -> str:
            buf.write(text + "\n")
            return text

        return read

    ui.banner(buf, color=True, version=VERSION)
    ui.ask_placement(buf, answer("2"), Path("/home/ada/web"), Path("/home/ada"), "home", True)
    ui.ask_agents(buf, answer("1 2"), hosts, ["opencode"], True)
    ui.render_review(
        buf,
        Path("/home/ada/.lazyplan/lazyplan.db"),
        Path("/home/ada/.lazyplan/templates"),
        [Path("/home/ada/.config/opencode/skills/lazyplan/SKILL.md")],
        Path("/home/ada/.lazyplan/setup.json"),
        Path("/home/ada/web/.agents/lazyplan/config.json"),
        True,
        plugins=[("opencode", Path("/home/ada/.config/opencode/plugins/lazyplan.js"))],
    )
    ui.confirm(buf, answer("y"), True)
    ui.success(
        buf,
        Path("/home/ada/.lazyplan/lazyplan.db"),
        [Path("/home/ada/.config/opencode/skills/lazyplan/SKILL.md")],
        [],
        True,
        plugins=[Path("/home/ada/.config/opencode/plugins/lazyplan.js")],
    )
    await _capture_transcript(store, target, buf.getvalue(), "lpui setup", (120, 42))


# -- manifest -------------------------------------------------------------

GROUPS = [
    ("shell", "Main shell", "The tree, overview, panes, themes, and terminal widths."),
    ("trust", "Trust hubs", "Criteria, evidence, questions, and references."),
    ("coordination", "Coordination hubs", "Claims, sessions, comments, and handoffs."),
    ("provenance", "Provenance hubs", "Pull requests and the activity feed."),
    ("source", "Source trail", "Repos, commits, files, diffs, and empty states."),
    ("forms", "Dialogs and forms", "Create, edit, prove, confirm, export, update, and overlays."),
    ("cli", "CLI and setup", "The shell surfaces that share the same journal."),
]


def _manifest_row(scene: Scene, out_dir: Path) -> dict[str, Any]:
    png = out_dir / f"{scene.id}.png"
    width, height = (int(part) for part in cs.dimensions(png).split("x"))
    return {
        "id": scene.id,
        "group": scene.group,
        "title": scene.title,
        "state": scene.state,
        "description": scene.description,
        "lookFor": list(scene.look_for),
        "keys": scene.keys,
        "image": f"{scene.id}.png",
        "webp": f"{scene.id}.webp",
        "width": width,
        "height": height,
    }


def write_manifest(names: list[str], out_dir: Path) -> None:
    """Merge captured rows into the manifest so --only stays safe."""
    target = out_dir / "scenes.json"
    existing: dict[str, dict[str, Any]] = {}
    if target.is_file():
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
            existing = {row["id"]: row for row in payload.get("scenes", [])}
        except (OSError, ValueError, KeyError):
            existing = {}
    by_id = {scene.id: scene for scene in scenes()}
    for name in names:
        existing[name] = _manifest_row(by_id[name], out_dir)
    rows = [existing[scene.id] for scene in by_id.values() if scene.id in existing]
    groups = [
        {
            "id": group_id,
            "title": title,
            "blurb": blurb,
            "count": sum(1 for row in rows if row["group"] == group_id),
        }
        for group_id, title, blurb in GROUPS
    ]
    manifest = {
        "version": VERSION,
        "generated": "2026-11-10",
        "groups": groups,
        "scenes": rows,
    }
    target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {cs.shown(target)} ({len(rows)} scenes)")


def run(out_dir: Path, only: list[str]) -> None:
    os.environ.setdefault("LAZYPLAN_NO_SPINNER", "1")
    os.environ.setdefault("LAZYPLAN_NO_UPDATE_CHECK", "1")
    all_scenes = scenes()
    by_id = {scene.id: scene for scene in all_scenes}
    names = only or list(by_id)
    unknown = [name for name in names if name not in by_id]
    if unknown:
        raise SystemExit(f"error: unknown scene(s): {', '.join(unknown)}")

    real_snapshot = cs.metrics.snapshot

    def frozen_snapshot(store: Store, now: float | None = None, **kwargs: object):
        return real_snapshot(store, now=cs.FIXED_NOW, **kwargs)

    with (
        cs.mock.patch("lazyplan.store.base.time.time", return_value=cs.STAMP),
        cs.mock.patch("lazyplan.services.metrics.snapshot", side_effect=frozen_snapshot),
        tempfile.TemporaryDirectory(prefix="lpui-ux-") as tmp,
    ):
        for name in names:
            scene = by_id[name]
            scene_dir = Path(tmp) / name
            scene_dir.mkdir(parents=True, exist_ok=True)
            store = scene.build(scene_dir)
            svg = Path(tmp) / f"{name}.svg"
            asyncio.run(scene.capture(store, svg))
            cs.patch_svg(svg)
            png = out_dir / f"{name}.png"
            out_dir.mkdir(parents=True, exist_ok=True)
            cs.convert(svg, png)
            print(f"wrote {cs.shown(png)} ({cs.dimensions(png)})")

    write_manifest(names, out_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"output directory (default: {DEFAULT_OUT.relative_to(ROOT)})",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="generate only this scene id (repeatable)",
    )
    args = parser.parse_args(argv)
    run(args.out.resolve(), args.only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
