#!/usr/bin/env python3
"""Regenerate the site's TUI and terminal screenshots from deterministic fixtures.

Usage:
  .venv/bin/python tools/capture-screens.py [--out DIR] [--only NAME ...]
                                            [--keep-svg PATH] [--no-og]

Builds throwaway git repos, plan databases, and fixed transcripts, opens the
real TUI or a terminal-like screen, exports SVG, then converts to PNG and WebP
for the site. Every fixture uses fixed dates, synthetic actors, and a fictional
`acme/web` remote, so two runs produce byte-identical images and no personal
data appears.

Requires git, ImageMagick 7 with librsvg and WebP, and textual in the running
Python (use `.venv/bin/python`).
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from collections.abc import Awaitable, Callable, Iterable
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, replace
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from rich.text import Text  # noqa: E402
from textual.app import App, ComposeResult  # noqa: E402
from textual.widgets import DirectoryTree, OptionList, Static, Tree  # noqa: E402

from lazyplan import services  # noqa: E402
from lazyplan.core.entities import Status  # noqa: E402
from lazyplan.core.policies.agents import DEFAULT_MODELS, HOSTS, TIERS  # noqa: E402
from lazyplan.infrastructure.environment import InstallInfo  # noqa: E402
from lazyplan.infrastructure.host_models import HostCatalog  # noqa: E402
from lazyplan.presentation.cli.parser import package_version  # noqa: E402
from lazyplan.presentation.setup.constants import REPO as PLACEMENT_REPO  # noqa: E402
from lazyplan.presentation.setup.session import (  # noqa: E402
    SetupDraft,
    SetupSession,
)
from lazyplan.presentation.setup.state import SetupState  # noqa: E402
from lazyplan.presentation.tui import create_app  # noqa: E402
from lazyplan.presentation.tui.controllers.notifications import (  # noqa: E402
    NotificationLog,
)
from lazyplan.presentation.tui.screens import (  # noqa: E402
    DraftScreen,
    NotificationLogScreen,
    SetupWizardScreen,
    UpdateScreen,
)
from lazyplan.presentation.tui.screens.export import ExportScreen  # noqa: E402
from lazyplan.presentation.tui.screens.source import SourceScreen  # noqa: E402
from lazyplan.services import drafts as draft_services  # noqa: E402
from lazyplan.services import metrics  # noqa: E402
from lazyplan.store import Store  # noqa: E402

SIZE = (130, 35)
TRANSCRIPT_SIZE = (120, 22)
CLI_SIZE = (130, 22)
DEFAULT_OUT = ROOT / "site" / "public" / "screens"
FIXTURE_ROOT = Path(tempfile.gettempdir()) / "lpui-fixtures"

#: Scenes the site itself publishes. The full review surface lives in
#: ``site/public/ux``; running with ``--only`` still writes any scene anywhere.
SITE_SCENES = frozenset(
    {
        "lpui-control-room",
        "lpui-detail",
        "lpui-dispatch",
        "lpui-drafts",
        "lpui-git-pane",
        "lpui-icons",
        "lpui-notification-log",
        "lpui-setup",
        "lpui-setup-review",
        "lpui-source-trail",
        "lpui-timeline",
        "lpui-trace",
        "lpui-update",
        "lpui-worktrees",
    }
)
DATE = "2026-10-01T09:00:00+00:00"
AUTHOR = "Ada Lovelace"
EMAIL = "ada@acme.dev"
REMOTE = "git@github.com:acme/web.git"
STAMP = 1767261600.0  # 2026-01-01 09:00 UTC, safely older than the attention window
FIXED_NOW = STAMP + 120.0  # two minutes after the fixture events

BASE_FILES = {
    "app/source.py": "def trail():\n    return []\n",
    "app/diff.py": "def render():\n    return ''\n",
    "app/link.py": "def link():\n    return None\n",
    "docs/usage.md": "# usage\n\nPress g.\n",
}
FEATURE_FILES = {
    "app/source.py": ("def trail(repo):\n    commits = repo.commits()\n    return commits\n"),
    "app/diff.py": ("def render(diff):\n    return [line for line in diff]\n"),
    "docs/usage.md": "# usage\n\nPress g, then pick a file.\n",
}
LINK_FILES = {
    "app/link.py": "def link(task, sha):\n    return task.attach(sha)\n",
    "docs/usage.md": "# usage\n\nPress g, then pick a file or commit.\n",
}
DOCS_FILES = {
    "docs/usage.md": "# usage\n\nPress g, then pick a file or commit.\n",
    "docs/keys.md": "# keys\n\ng opens the source trail.\n",
}
PRS = (
    (42, "Render diffs in place", "merged", "pass"),
    (43, "Show changed files", "open", "pending"),
)
COMMITS = (
    ("Render diffs", FEATURE_FILES),
    ("Link task commits", LINK_FILES),
    ("Document the trail", DOCS_FILES),
)


def git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        encoding="utf-8",
        env=env,
    )
    return proc.stdout


def commit_env() -> dict[str, str]:
    env = dict(os.environ)
    for key in ("GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE"):
        env[key] = DATE
    env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = AUTHOR
    env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = EMAIL
    return env


def write_files(repo: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")


def commit(repo: Path, message: str, files: dict[str, str]) -> str:
    write_files(repo, files)
    git(repo, "add", ".")
    git(repo, "commit", "-qm", message, env=commit_env())
    return git(repo, "rev-parse", "HEAD").strip()


def build_source_fixture(tmp: Path) -> Store:
    repo = tmp / "web"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", EMAIL)
    git(repo, "config", "user.name", AUTHOR)
    base = commit(repo, "Add source trail scaffolding", BASE_FILES)
    linked = []
    for subject, files in COMMITS:
        linked.append((subject, commit(repo, subject, files), tuple(files)))
    git(repo, "remote", "add", "origin", REMOTE)

    store = Store(str(tmp / "plan.db"))
    plan = store.add_plan(
        "Ship the source trail",
        "Read the commits, changed files, and pull requests behind each task"
        " without leaving the plan.",
        goal="Know where a task landed and whether its evidence is current.",
    )
    store.add_criteria("plan", plan.id, "Every task links the commit it shipped")
    store.add_criteria("plan", plan.id, "Missing proof is marked stale, never hidden")
    milestone = store.add_milestone(plan.id, "Read diffs in place")
    task = store.add_task(
        milestone.id,
        "Render unified diffs",
        "Show additions and removals inline for the selected commit.",
    )
    store.add_repo_link("task", task.id, str(repo), REMOTE, branch="main", base_sha=base)
    for subject, sha, files in linked:
        store.link_commit(
            "task",
            task.id,
            sha,
            subject=subject,
            author=AUTHOR,
            repo_root=str(repo),
            files=files,
        )
    for number, title, state, checks in PRS:
        store.link_forge(
            "task",
            task.id,
            number,
            url=f"https://github.com/acme/web/pull/{number}",
            title=title,
            state=state,
            checks=checks,
        )
    return store


def build_empty_fixture(tmp: Path) -> Store:
    """A fresh journal for the setup and update screens."""
    return Store(str(tmp / "plan.db"))


DRAFT_DOCUMENT = {
    "plan": {
        "key": "draft-review",
        "title": "Review a plan before it ships",
        "why": "Reviews land as anchored notes on the draft, so feedback is resolved before the plan joins the queue.",
        "what": "## Scope\n\n- In scope: draft blocks, anchored notes, and promotion.\n- Out of scope: editing a promoted plan.",
        "criteria": [
            "A draft takes anchored notes.",
            "Promotion waits for every open note.",
        ],
        "dispatch_mode": "serial",
        "max_agents": 1,
    },
    "milestones": [
        {
            "key": "review",
            "title": "Review the draft",
            "desc": "As a reviewer, I want to leave anchored feedback, so that the plan improves before it ships.\n\nInputs: one submitted draft.\n\nCommit slices: the screen, the notes, and promotion.",
            "criteria": [
                "Given a submitted draft, when a quote is selected, then the note anchors to that block."
            ],
            "lane_group": 1,
            "agent_role": "implementer",
            "tasks": [
                {
                    "key": "annotate",
                    "title": "Annotate a block",
                    "desc": "Approach: select the block or quote and leave one comment, question, or change.\n\nInputs: the draft review screen.\n\nCommit slice: the annotation slice.\n\nVerify: the note lands on the chosen block.",
                    "criteria": ["A note names its block and quote."],
                    "role": "implementer",
                }
            ],
        }
    ],
}


def build_draft_fixture(tmp: Path) -> Store:
    """A draft with anchored notes, ready for the review screen."""
    store = Store(str(tmp / "plan.db"))
    draft = draft_services.create(store, DRAFT_DOCUMENT, actor="agent")
    draft_services.annotate(
        store,
        draft.id,
        "plan:why",
        "comment",
        "Say why review lives before the queue, not after it.",
        author="reviewer",
    )
    draft_services.annotate(
        store,
        draft.id,
        "task:annotate:desc",
        "question",
        "Which block owns a selection that spans two tasks?",
        quote="select the block or quote",
        author="reviewer",
    )
    draft_services.annotate(
        store,
        draft.id,
        "plan:criterion:1",
        "change",
        "Name the promotion rule exactly: open notes block it.",
        quote="every open note",
        author="reviewer",
    )
    return store


def build_dispatch_fixture(tmp: Path) -> Store:
    """A parallel plan with three lanes and one registered lane worktree."""
    from lazyplan.core.policies.worktrees import derive_lane_worktree

    repo = tmp / "web"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", EMAIL)
    git(repo, "config", "user.name", AUTHOR)
    base = commit(repo, "Add the API scaffolding", BASE_FILES)
    git(repo, "remote", "add", "origin", REMOTE)

    store = Store(str(tmp / "plan.db"))
    plan = store.add_plan(
        "Passwordless sign-in",
        "Ship magic links and passkeys without breaking the password path.",
        goal="Sign in without a password, safely and reversibly.",
        dispatch_mode="parallel",
        max_agents=2,
    )
    read = store.add_milestone(plan.id, "Read path", lane_group=1, agent_role="implementer")
    write = store.add_milestone(plan.id, "Write path", lane_group=1, agent_role="docs")
    integrate = store.add_milestone(plan.id, "Integration", lane_group=2, agent_role="integrator")
    store.add_task(
        read.id, "Add the token model", "Wire the model and migration.", role="implementer"
    )
    store.add_task(read.id, "Exchange the magic link", "Verify and redeem.", role="implementer")
    store.add_task(write.id, "Document the sign-in flow", "Guide and reference.", role="docs")
    store.add_task(integrate.id, "Merge the lanes", "Run the combined gate.", role="integrator")
    store.add_repo_link("plan", plan.id, str(repo), REMOTE, branch="main", base_sha=base)

    for lane in (read, write):
        target = derive_lane_worktree(str(repo), plan.id, plan.name, lane.id, lane.title)
        store.register_plan_worktree(
            plan.id,
            str(repo),
            target.worktree_path,
            branch=target.branch,
            repo_remote=REMOTE,
            actor="Ada",
            registered_at=STAMP,
            milestone_id=lane.id,
        )
    read_target = derive_lane_worktree(str(repo), plan.id, plan.name, read.id, read.title)
    services.set_status(
        store,
        "task",
        store.list_tasks(read.id)[0].id,
        Status.DOING,
        actor="Ada",
        worktree=read_target.worktree_path,
    )
    return store


def cli_text(store: Store, *args: str) -> str:
    """Run one real CLI invocation against *store* and return stdout and stderr."""
    from lazyplan.presentation.cli import main

    out = io.StringIO()
    err = io.StringIO()
    argv = ["--db", str(store.path), *args]
    try:
        with redirect_stdout(out), redirect_stderr(err):
            main(argv)
    except SystemExit:
        pass
    text = out.getvalue() + err.getvalue()
    return text.rstrip() + "\n"


def cli_transcript(store: Store, *args: str) -> Text:
    """A command line plus its real output, styled like the other transcripts."""
    command = "lpui " + " ".join(args)
    body = Text()
    body.append(f"$ {command}\n", style="bold #22d3ee")
    for line in cli_text(store, *args).splitlines():
        body.append(line + "\n", style="#e4e4e7")
    return body


def next_minor(version: str) -> str:
    """The next minor release of *version*, for the deterministic update screen."""
    parts = version.split(".")
    if len(parts) < 3 or not parts[0].isdigit() or not parts[1].isdigit():
        return version
    return f"{parts[0]}.{int(parts[1]) + 1}.0"


def fixture_catalogs(
    hosts: Iterable[str], _home: Path, _root: Path | None
) -> dict[str, HostCatalog]:
    """Deterministic host catalogs: no binaries, no real home config."""
    return {
        host: HostCatalog(
            host=host,
            label=host.title(),
            models=tuple(
                value
                for tier in TIERS
                for value in (DEFAULT_MODELS.get(tier, {}).get(host, ""),)
                if value
            ),
            tier_defaults={
                tier: DEFAULT_MODELS.get(tier, {}).get(host, "")
                for tier in TIERS
                if DEFAULT_MODELS.get(tier, {}).get(host, "")
            },
            source="fixture",
        )
        for host in HOSTS
        if host in hosts
    }


def build_setup_session() -> SetupSession:
    """A deterministic first-run wizard: two agents, repo placement, effort levels."""
    from lazyplan.presentation.setup import models

    home = Path("/home/ada")
    repo = Path("/home/ada/web")
    profiles_map, tiers = models.initial_maps(
        home / ".lazyplan" / "lazyplan.db",
        home,
        repo,
        ["opencode", "claude"],
        fixture_catalogs,
    )
    draft = SetupDraft(
        placement=PLACEMENT_REPO,
        agents=["opencode", "claude"],
        skills_enabled=True,
        hooks_mode="strict",
        agents_pointer=True,
        profiles_map=profiles_map,
        tiers_map=tiers,
    )
    for role, effort in (("implementer", "low"), ("qa", "medium"), ("reviewer", "high")):
        profile = draft.profiles_map.get(role)
        if profile is not None:
            draft.profiles_map[role] = replace(profile, effort=effort)
    return SetupSession(
        cwd=repo,
        home=home,
        version=package_version(),
        root=repo,
        state=SetupState(
            placement=PLACEMENT_REPO,
            agents=["opencode", "claude"],
            hooks=True,
            skills_enabled=True,
            agents_pointer=True,
        ),
        draft=draft,
        catalogs=fixture_catalogs(["opencode", "claude"], home, repo),
        pending=(),
    )


def build_export_fixture(tmp: Path) -> Store:
    """A plan with a deterministic Downloads tree for the export picker shot."""
    store = build_source_fixture(tmp)
    downloads = tmp / "Downloads"
    (downloads / "team").mkdir(parents=True)
    (downloads / "archive").mkdir()
    return store


def build_timeline_fixture(tmp: Path) -> Store:
    """A plan with sequential milestones and tasks for the scoped timeline shot."""
    store = Store(str(tmp / "plan.db"))
    plan = store.add_plan(
        "Ship the scoped timeline",
        "Show only the clicked row and its immediate children.",
        goal="Keep the timeline focused on the work in front of you.",
    )
    first = store.add_milestone(plan.id, "Scope the lane filter")
    second = store.add_milestone(plan.id, "Render one row at a time")
    third = store.add_milestone(plan.id, "Publish the patch")
    regression = store.add_task(first.id, "Write the regression test")
    drop = store.add_task(first.id, "Drop ancestor lanes")
    bold = store.add_task(first.id, "Keep the clicked lane bold")
    store.add_task(second.id, "Update the empty copy")
    store.add_task(second.id, "Refresh the screenshot")
    store.add_task(third.id, "Cut 0.30.3")

    def at(stamp: float, action: Callable[[], object]) -> object:
        with mock.patch("lazyplan.store.base.time.time", return_value=stamp):
            return action()

    at(STAMP + 20, lambda: services.set_status(store, "task", regression.id, Status.DOING))
    at(STAMP + 40, lambda: services.set_status(store, "task", regression.id, Status.DONE))
    at(STAMP + 20, lambda: services.set_status(store, "milestone", first.id, Status.DOING))
    at(STAMP + 40, lambda: services.set_status(store, "task", drop.id, Status.DOING))
    at(STAMP + 65, lambda: services.set_status(store, "task", drop.id, Status.DONE))
    at(STAMP + 65, lambda: services.set_status(store, "task", bold.id, Status.DOING))
    at(STAMP + 100, lambda: services.set_status(store, "milestone", first.id, Status.DONE))
    at(STAMP + 100, lambda: services.set_status(store, "task", bold.id, Status.DONE))
    return store


def build_coordination_fixture(tmp: Path) -> Store:
    """A journal with active and expired claims, a block, aging, gaps, and red checks."""
    store = Store(str(tmp / "plan.db"))
    plan = store.add_plan(
        "Ship the coordination release",
        "Coordinate the queue, keep proof with the work, and surface flow risk.",
        goal="One shared plan that two agents can work without racing.",
    )
    milestone = store.add_milestone(
        plan.id,
        "Coordinate the queue",
        "Leases, handoffs, and the control strip.",
    )
    claimed = store.add_task(milestone.id, "Claim the release queue", "Commit slice: queue.")
    expired = store.add_task(milestone.id, "Reclaim the abandoned lease", "Commit slice: lease.")
    blocked = store.add_task(milestone.id, "Wait on the infra window", "Commit slice: infra.")
    aging = store.add_task(milestone.id, "Review the flow health", "Commit slice: stats.")
    gap = store.add_task(milestone.id, "Close with an open criterion", "Commit slice: docs.")
    red = store.add_task(milestone.id, "Gate on the red checks", "Commit slice: gate.")
    store.add_task(milestone.id, "Unclaimed follow-up", "Commit slice: follow-up.")

    with mock.patch("lazyplan.store.base.time.time", return_value=STAMP):
        services.set_status(store, "task", claimed.id, Status.DOING, actor="Ada")
        services.set_status(store, "task", aging.id, Status.DOING, actor="Ada")
        services.set_status(store, "task", gap.id, Status.DONE, actor="Ada")
        services.set_status(store, "task", red.id, Status.DONE, actor="Ada")
    services.block_task(store, blocked.id, "waiting on the infra window", actor="Ada")

    store.claim_task(
        claimed.id,
        "Ada",
        ttl_seconds=10 * 365 * 24 * 3600,
        note="Reviewing the release queue",
    )
    store.claim_task(expired.id, "Lin", ttl_seconds=60, now=STAMP)
    store.add_note("task", claimed.id, "Handoff: the queue is current as of today.", actor="Ada")
    store.add_comment("task", claimed.id, "Please cover the retry path, @bob.", actor="Ada")
    store.add_comment("task", claimed.id, "Checked the queue against main.", actor="Bob")
    store.add_criteria("task", gap.id, "Cover the retry path")
    store.link_forge(
        "task",
        red.id,
        42,
        url="https://github.com/acme/web/pull/42",
        title="Render diffs in place",
        state="open",
        checks="fail",
    )
    return store


def build_control_room_fixture(tmp: Path) -> Store:
    """The coordination journal plus approval drift, a question, refs, and sessions."""
    store = build_coordination_fixture(tmp)
    plan = next(plan for plan in store.list_plans() if plan.name == "Ship the coordination release")
    services.revisions.approve(store, plan.id, actor="Ada")
    task = next(
        task
        for task in store.list_tasks(store.list_milestones(plan.id)[0].id)
        if task.title == "Claim the release queue"
    )
    store.update_task(task.id, title="Claim the release queue (v2)", reason="scope change")
    services.add_question(store, plan.id, "Which host ships first?", actor="Ada")
    store.link_ref(
        plan.id,
        "https://github.com/acme/web/issues/7",
        title="Epic: coordination",
        kind="epic",
        actor="Ada",
    )
    return store


class TranscriptApp(App[None]):
    """A dark terminal-like screen for deterministic command transcripts."""

    CSS = """
    Screen { background: #09090b; color: #e4e4e7; }
    #term { padding: 1 2; }
    """

    def __init__(self, body: Text, title: str) -> None:
        super().__init__()
        self._body = body
        self.title = title

    def compose(self) -> ComposeResult:
        yield Static(self._body, id="term")


def transcript(*lines: tuple[str, str]) -> Text:
    """Build a monospace transcript from (text, style) pairs."""
    body = Text()
    for text, style in lines:
        body.append(text + "\n", style=style)
    return body


def _task_id(store: Store, title: str) -> int:
    for plan in store.list_plans():
        for milestone in store.list_milestones(plan.id):
            for task in store.list_tasks(milestone.id):
                if task.title == title:
                    return task.id
    raise SystemExit(f"fixture task not found: {title}")


def _nodes(tree: Tree[object], kind: str) -> list[object]:
    found: list[object] = []

    def walk(node: object) -> None:
        for child in getattr(node, "children", []):
            data = getattr(child, "data", None)
            if isinstance(data, dict) and data.get("kind") == kind:
                found.append(child)
            walk(child)

    walk(tree.root)
    return found


async def capture_source(store: Store, target: Path) -> None:
    task_id = _task_id(store, "Render unified diffs")
    app = create_app(str(store.path))
    async with app.run_test(size=SIZE) as pilot:
        app.push_screen(SourceScreen(store, "task", task_id))
        await pilot.pause()
        tree = app.screen.query_one("#source-tree", Tree)
        repo_node = tree.root.children[0]
        repo_node.expand()
        feature_node = next(
            child
            for child in repo_node.children
            if child.data.get("kind") == "commit" and "Render diffs" in str(child.label)
        )
        feature_node.expand()
        for _ in range(20):
            if any("M " in str(child.label) for child in feature_node.children):
                break
            await pilot.pause(0.05)
        tree.focus()
        await pilot.pause()
        tree.select_node(feature_node.children[0])
        await pilot.pause()
        app.save_screenshot(str(target))


async def _capture_task_shell(store: Store, target: Path, theme: str | None = None) -> None:
    """Capture the main shell with a linked task selected and expanded."""
    patch = (
        mock.patch.dict(os.environ, {"LAZYPLAN_THEME": theme})
        if theme is not None
        else mock.patch.dict(os.environ, {}, clear=False)
    )
    task_id = _task_id(store, "Render unified diffs")
    with patch:
        app = create_app(str(store.path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            tree = app.query_one("#tree", Tree)
            app.tree_controller.expand_all()
            tree.focus()
            selected = next(
                (
                    node
                    for node in _nodes(tree, "task")
                    if getattr(node, "data", {}).get("id") == task_id
                ),
                None,
            )
            if selected is not None:
                tree.select_node(selected)
            await pilot.pause(0.5)
            app.save_screenshot(str(target))


async def capture_git_pane(store: Store, target: Path) -> None:
    await _capture_task_shell(store, target)


async def capture_export(store: Store, target: Path) -> None:
    """Capture the Markdown export picker with a deterministic Downloads tree."""
    plan_id = next(plan.id for plan in store.list_plans() if plan.name == "Ship the source trail")
    root = Path(store.path).parent
    downloads = root / "Downloads"
    with mock.patch.dict(os.environ, {"HOME": str(root), "USERPROFILE": str(root)}):
        app = create_app(str(store.path))
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            app.push_screen(
                ExportScreen(
                    store,
                    plan_id,
                    "Ship the source trail",
                    default_dir=downloads,
                )
            )
            await pilot.pause()
            tree = app.screen.query_one("#export-tree", DirectoryTree)
            tree.root.expand()
            await pilot.pause()
            folder = next(child for child in tree.root.children if "team" in str(child.label))
            tree.select_node(folder)
            await pilot.pause()
            app.save_screenshot(str(target))


async def capture_theme_void(store: Store, target: Path) -> None:
    await _capture_task_shell(store, target, "void")


async def capture_theme_latte(store: Store, target: Path) -> None:
    await _capture_task_shell(store, target, "latte")


async def capture_timeline(store: Store, target: Path) -> None:
    """Capture the shell with the timeline open and a milestone selected."""
    app = create_app(str(store.path))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        app.action_toggle_timeline()
        tree = app.query_one("#tree", Tree)
        app.tree_controller.expand_all()
        tree.focus()
        milestones = _nodes(tree, "milestone")
        if milestones:
            tree.select_node(milestones[0])
            await pilot.pause()
            milestones = _nodes(tree, "milestone")
            if milestones:
                milestones[0].expand()
        await pilot.pause(0.5)
        app.save_screenshot(str(target))


async def capture_coordination(store: Store, target: Path) -> None:
    app = create_app(str(store.path))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        tree = app.query_one("#tree", Tree)
        app.tree_controller.expand_all()
        tree.focus()
        tasks = _nodes(tree, "task")
        if tasks:
            tree.select_node(tasks[0])
        await pilot.pause()
        app.save_screenshot(str(target))


async def capture_control_room(store: Store, target: Path) -> None:
    plan_id = next(
        plan.id for plan in store.list_plans() if plan.name == "Ship the coordination release"
    )
    app = create_app(str(store.path))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        tree = app.query_one("#tree", Tree)
        app.tree_controller.expand_all()
        tree.focus()
        plans = _nodes(tree, "plan")
        if plans:
            tree.select_node(plans[0])
        tasks = _nodes(tree, "task")
        if tasks:
            tree.select_node(tasks[0])
        await pilot.pause()
        app.selected = ("plan", plan_id)
        app.update_preview(force=True)
        app.tree_controller.expand_all()
        await pilot.pause(0.2)
        app.save_screenshot(str(target))


async def capture_plan_detail(store: Store, target: Path) -> None:
    plan_id = next(plan.id for plan in store.list_plans() if plan.name == "Ship the source trail")
    app = create_app(str(store.path))
    async with app.run_test(size=SIZE) as pilot:
        app.selected = ("plan", plan_id)
        app.update_preview(force=True)
        await pilot.pause()
        app.save_screenshot(str(target))


async def capture_collaboration(store: Store, target: Path) -> None:
    task_id = _task_id(store, "Claim the release queue")
    app = create_app(str(store.path))
    async with app.run_test(size=SIZE) as pilot:
        app.selected = ("task", task_id)
        app.update_preview(force=True)
        await pilot.pause()
        app.save_screenshot(str(target))


async def capture_setup_step(store: Store, target: Path, start: str) -> None:
    """Open the setup wizard at one step with a deterministic draft."""
    session = build_setup_session()
    app = create_app(str(store.path))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        app.push_screen(SetupWizardScreen(session, start))
        await pilot.pause(0.6)
        app.save_screenshot(str(target))


async def capture_setup(store: Store, target: Path) -> None:
    await capture_setup_step(store, target, "")


async def capture_setup_review(store: Store, target: Path) -> None:
    await capture_setup_step(store, target, "review")


async def capture_update(store: Store, target: Path) -> None:
    """The update dialog for a newer release, from a pipx install."""
    installed = package_version()
    app = create_app(str(store.path))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        app.push_screen(
            UpdateScreen(
                installed,
                next_minor(installed),
                InstallInfo(method="pipx", upgradeable=True),
            )
        )
        await pilot.pause()
        app.save_screenshot(str(target))


def _local_stamp(clock: str) -> float:
    """A fixed wall-clock time that renders the same in every timezone."""
    return time.mktime(time.strptime(f"2026-01-01 {clock}", "%Y-%m-%d %H:%M:%S"))


LOG_ENTRIES = (
    ("information", "Setup applied: home placement, one agent.", "setup"),
    ("information", "Draft D4 submitted for revision.", "drafts"),
    ("warning", "Claim on T12 expires in ten minutes.", "claims"),
    ("information", "Icons: orbit remembered.", "appearance"),
    ("warning", "Task T9 is blocked: waiting for CI.", "tasks"),
    ("error", "Pull request #42 has a failing check.", "pull requests"),
)


async def capture_draft(store: Store, target: Path) -> None:
    """The draft review screen with a block selected and notes beside it."""
    draft = draft_services.list_drafts(store)[0]
    app = create_app(str(store.path))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        app.push_screen(DraftScreen(store, draft.id))
        await pilot.pause(0.6)
        annotations = app.screen.query_one("#draft-annotations", OptionList)
        if annotations.option_count:
            annotations.highlighted = 0
        await pilot.pause(0.2)
        app.save_screenshot(str(target))


async def capture_notification_log(store: Store, target: Path) -> None:
    """The session log with fixed clocks, at the newest entry."""
    clocks = iter(
        _local_stamp(clock)
        for clock in ("09:12:30", "09:13:02", "09:13:40", "09:14:05", "09:14:31", "09:15:10")
    )
    log = NotificationLog(clock=lambda: next(clocks))
    for severity, message, source in LOG_ENTRIES:
        log.append(message, severity=severity, source=source)
    app = create_app(str(store.path))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        app.push_screen(NotificationLogScreen(log))
        await pilot.pause(0.4)
        app.save_screenshot(str(target))


async def capture_icons_orbit(store: Store, target: Path) -> None:
    """The shell on the orbit icon palette."""
    with mock.patch.dict(os.environ, {"LAZYPLAN_ICONS": "orbit"}):
        await _capture_task_shell(store, target)


def _dispatch_text() -> Text:
    return transcript(
        ("$ lpui dispatch --plan 7", "bold #22d3ee"),
        ("P7 Sign-in · parallel · max 2", "#fafafa"),
        ("now      wave 1 · capacity 1/2 active, 1 available", "#e4e4e7"),
        ("lanes:", "#e4e4e7"),
        ("  M1 Read path [active] w1 implementer", "#e4e4e7"),
        ("    T2 Exchange the magic link (implementer)", "#a1a1aa"),
        ("    registered: /home/ada/web--plan-7-sign-in--m1-read-path", "#71717a"),
        ("  M2 Write path [ready] w1 docs", "#e4e4e7"),
        ("    T3 Document the sign-in flow (docs)", "#a1a1aa"),
        ("    registered: /home/ada/web--plan-7-sign-in--m2-write-path", "#71717a"),
        ("  M3 Integration [waiting] w2 integrator", "#e4e4e7"),
        ("    T4 Merge the lanes (integrator)", "#a1a1aa"),
        ("    blocked: wave 2 waits for wave 1", "#fbbf24"),
        ("dispatchable:", "#e4e4e7"),
        ("  M2 T3 Document the sign-in flow (docs)", "#4ade80"),
        (
            "    lpui claim --id 3 --worktree /home/ada/web--plan-7-sign-in--m2-write-path",
            "#a1a1aa",
        ),
        ("actions:", "#e4e4e7"),
        ("  lpui plan worktree add --id 7 --milestone 3 --repo /home/ada/web", "#a1a1aa"),
        ("  lpui claim --id 3 --worktree /home/ada/web--plan-7-sign-in--m2-write-path", "#a1a1aa"),
    )


def _worktrees_text() -> Text:
    return transcript(
        ("$ lpui plan worktree list --id 7", "bold #22d3ee"),
        ("plan 7: Sign-in", "#fafafa"),
        (
            "  M1 /home/ada/web -> /home/ada/web--plan-7-sign-in--m1-read-path"
            " [plan/7-sign-in--m1-read-path]",
            "#e4e4e7",
        ),
        (
            "  M2 /home/ada/web -> /home/ada/web--plan-7-sign-in--m2-write-path"
            " [plan/7-sign-in--m2-write-path]",
            "#e4e4e7",
        ),
        ("", ""),
        ("$ lpui plan worktree print --id 7 --milestone 3", "bold #22d3ee"),
        ("plan 7: Sign-in", "#fafafa"),
        ("repo /home/ada/web", "#e4e4e7"),
        (
            "  git -C /home/ada/web worktree add -b plan/7-sign-in--m3-integration"
            " /home/ada/web--plan-7-sign-in--m3-integration HEAD",
            "#4ade80",
        ),
        ("", ""),
        ("$ lpui plan worktree add --id 7 --milestone 3 --repo /home/ada/web", "bold #22d3ee"),
        ("registered plan 7 worktree /home/ada/web--plan-7-sign-in--m3-integration", "#4ade80"),
        ("on plan/7-sign-in--m3-integration", "#4ade80"),
    )


def _flow_health_text() -> Text:
    return transcript(
        ("$ lpui stats --since 30.days", "bold #22d3ee"),
        ("wip        2 doing", "#e4e4e7"),
        ("cycle      median 95 min", "#e4e4e7"),
        ("throughput 4 done in window", "#e4e4e7"),
        ("aging      median 210 min · max 480 min", "#e4e4e7"),
        ("stale      1 todo past threshold", "#e4e4e7"),
        ("reopened   1", "#e4e4e7"),
        ("claims     1 active", "#e4e4e7"),
        ("blocked    1", "#e4e4e7"),
        ("", ""),
        ("$ lpui --porcelain stats --since 7.days", "bold #22d3ee"),
        ("metric\twip\t-\t2\t-\t-", "#a1a1aa"),
        ("metric\tcycle_median_minutes\t-\t95.0\t-\t-", "#a1a1aa"),
        ("metric\tthroughput\t-\t4\t-\t-", "#a1a1aa"),
        ("metric\tstale_todos\t-\t1\t-\t-", "#a1a1aa"),
        ("", ""),
        ("Attention: expired claims · blocked · aging doing · done gaps · red checks", "#4ade80"),
    )


def _trace_text() -> Text:
    return transcript(
        ("$ lpui trace --plan 1", "bold #22d3ee"),
        ("P1 Ship the source trail (doing)", "#fafafa"),
        ("criterion #7 [open] Works offline (plan #1)", "#e4e4e7"),
        ("  T3 Render unified diffs (M1)", "#e4e4e7"),
        ("    1a2b3c4d5e6f Render diffs", "#a1a1aa"),
        ("    PR #42 merged Render diffs in place", "#a1a1aa"),
        ("criterion #8 [open] Covers the retry path (plan #1)", "#e4e4e7"),
        ("  (no proving task)", "#f87171"),
        ("", ""),
        ("$ lpui lint --plan 1 --strict", "bold #22d3ee"),
        ("error uncovered-criterion criterion #8: criterion has no proving task", "#f87171"),
        ("error weak-task task #6: task description has no verification token", "#fbbf24"),
        ("exit 2", "#71717a"),
    )


def _mcp_text() -> Text:
    return transcript(
        ("$ lpui --actor helper mcp", "bold #22d3ee"),
        ('{"jsonrpc":"2.0","id":1,"method":"initialize"}', "#a1a1aa"),
        ('{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05",', "#e4e4e7"),
        ('  "capabilities":{"tools":{},"resources":{}},', "#e4e4e7"),
        ('  "serverInfo":{"name":"lazyplan","version":"0"}}}', "#e4e4e7"),
        ('{"jsonrpc":"2.0","id":2,"method":"tools/list"}', "#a1a1aa"),
        ('{"jsonrpc":"2.0","id":2,"result":{"tools":[', "#e4e4e7"),
        ('  {"name":"brief","annotations":{"readOnlyHint":true}},', "#e4e4e7"),
        ('  {"name":"trace","annotations":{"readOnlyHint":true}},', "#e4e4e7"),
        ('  {"name":"claim_task","annotations":{"readOnlyHint":false}}]}}', "#e4e4e7"),
        ('{"jsonrpc":"2.0","id":3,"method":"tools/call",', "#a1a1aa"),
        ('  "params":{"name":"brief","arguments":{"plan":1}}}', "#a1a1aa"),
        ('{"jsonrpc":"2.0","id":3,"result":{"content":[{"type":"text",', "#e4e4e7"),
        ('  "text":"{\\"active\\": 1, \\"doing\\": 2, \\"next\\": 3}"}]}}', "#4ade80"),
    )


def _share_sync_text() -> Text:
    return transcript(
        (
            '$ lpui comment add --kind task --id 3 --text "Please cover @bob\'s case"',
            "bold #22d3ee",
        ),
        ("comment #7 open Please cover @bob's case", "#e4e4e7"),
        ("", ""),
        ("$ lpui share --plan 1 --format html --out /tmp/plan.html", "bold #22d3ee"),
        ("shared P1 as html: /tmp/plan.html", "#4ade80"),
        ("", ""),
        ("$ lpui sync --file backup.json --dry-run", "bold #22d3ee"),
        ("dry-run: 1 added · 1 skipped · 1 conflict", "#e4e4e7"),
        ("  conflict API v2 (8f3c...): name, status", "#f87171"),
        ("  conflict reported without writing", "#71717a"),
    )


def _gates_text() -> Text:
    return transcript(
        ("$ lpui task finish --id 3 --require-checks", "bold #22d3ee"),
        ("error: completion gate: checks are fail", "#f87171"),
        ("exit 2 · task left doing · no commits linked", "#71717a"),
        ("", ""),
        (
            '$ lpui task finish --id 3 --require-checks --override "known flaky runner"',
            "bold #22d3ee",
        ),
        ("linked 2 commit(s) on feat/release from 1a2b3c4d5e6f", "#e4e4e7"),
        ("T3 done", "#4ade80"),
        ("", ""),
        ("note: Gate override by Ada: known flaky runner (prs=1, checks=fail)", "#fbbf24"),
        ("gate: fail · 1 PRs", "#fbbf24"),
    )


def _imports_text() -> Text:
    return transcript(
        ("$ lpui issue import --provider github --repo acme/web --dry-run", "bold #22d3ee"),
        ("dry-run: 2 created · 0 updated", "#e4e4e7"),
        ("  github 42 -> plan 0", "#a1a1aa"),
        ("  github 43 -> plan 0", "#a1a1aa"),
        ("", ""),
        ("$ lpui issue import --provider linear --file linear-export.json", "bold #22d3ee"),
        ("2 created · 1 updated", "#e4e4e7"),
        ("", ""),
        ("$ lpui plan show --id 2", "bold #22d3ee"),
        ("source: github #42 https://github.com/acme/web/issues/42", "#4ade80"),
        ("source: linear #ENG-4 https://linear.app/acme/issue/ENG-4", "#4ade80"),
        ("Re-import refreshes metadata only; no writeback.", "#71717a"),
    )


def _transcript_capture(
    text: Text, size: tuple[int, int], title: str
) -> Callable[[Store | None, Path], Awaitable[None]]:
    async def capture(_store: Store | None, target: Path) -> None:
        app = TranscriptApp(text, title)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            app.save_screenshot(str(target))

    return capture


@dataclass(frozen=True)
class Scene:
    """One deterministic screenshot and how to build it."""

    size: tuple[int, int]
    build: Callable[[Path], Store | None]
    capture: Callable[[Store | None, Path], Awaitable[None]]
    alt: str


def _no_fixture(_tmp: Path) -> Store | None:
    return None


SCENES: dict[str, Scene] = {
    "lpui-control-room": Scene(
        SIZE,
        build_control_room_fixture,
        capture_control_room,
        "lazyplan control room with the plan tree, a compact agents row, the needs line, an open question, approval drift, and a failed check.",
    ),
    "lpui-source-trail": Scene(
        SIZE,
        build_source_fixture,
        capture_source,
        "lazyplan source trail for a task showing a repository, commits, changed files, a merged pull request, and a unified diff.",
    ),
    "lpui-git-pane": Scene(
        SIZE,
        build_source_fixture,
        capture_git_pane,
        "lazyplan main shell with a linked task selected, showing the sticky preview above a GIT pane with the checkout, branch, clean state, commits, and pull requests.",
    ),
    "lpui-export": Scene(
        SIZE,
        build_export_fixture,
        capture_export,
        "lazyplan Markdown export picker showing a Downloads destination, folder tree, filename, and Export and Cancel actions.",
    ),
    "lpui-theme-void": Scene(
        SIZE,
        build_source_fixture,
        capture_theme_void,
        "lazyplan main shell in the OLED-black void theme, with the plan tree, sticky preview, and GIT pane.",
    ),
    "lpui-theme-latte": Scene(
        SIZE,
        build_source_fixture,
        capture_theme_latte,
        "lazyplan main shell in the light Latte theme, with the plan tree, sticky preview, and GIT pane.",
    ),
    "lpui-timeline": Scene(
        SIZE,
        build_timeline_fixture,
        capture_timeline,
        "lazyplan main shell with a milestone selected, showing only that milestone and its task lanes on the timeline.",
    ),
    "lpui-detail": Scene(
        SIZE,
        build_source_fixture,
        capture_plan_detail,
        "Plan overview showing the reason, scope, acceptance criteria, milestones, and linked source.",
    ),
    "lpui-drafts": Scene(
        SIZE,
        build_draft_fixture,
        capture_draft,
        "Draft review screen with the plan document on the left, a selected task block, and three anchored annotations with their kinds beside it.",
    ),
    "lpui-notification-log": Scene(
        SIZE,
        build_empty_fixture,
        capture_notification_log,
        "Notification log overlay listing six timestamped entries with severities and sources, newest at the bottom.",
    ),
    "lpui-icons": Scene(
        SIZE,
        build_source_fixture,
        capture_icons_orbit,
        "Main shell on the orbit icon palette: circular status marks, kind icons, and section glyphs across the plan tree, preview, and git pane.",
    ),
    "lpui-setup": Scene(
        SIZE,
        build_empty_fixture,
        capture_setup,
        "Setup wizard on its welcome step, with the step rail, the database, config, and pointer paths, and the Back, Next, and Finish later actions.",
    ),
    "lpui-setup-review": Scene(
        SIZE,
        build_empty_fixture,
        capture_setup_review,
        "Setup wizard on the review step, listing every database, config, skill, pointer, and agent profile file the apply will write, with Apply and Finish later actions.",
    ),
    "lpui-update": Scene(
        SIZE,
        build_source_fixture,
        capture_update,
        "Update dialog over a populated shell, showing the installed and latest versions, the install method, and the Download, Restart, and Later buttons.",
    ),
    "lpui-dispatch": Scene(
        CLI_SIZE,
        _no_fixture,
        _transcript_capture(_dispatch_text(), CLI_SIZE, "lpui dispatch"),
        "Terminal transcript of lpui dispatch showing a parallel plan, the current wave and capacity, three lanes with roles, registered worktrees, and the claim commands for the ready tasks.",
    ),
    "lpui-worktrees": Scene(
        CLI_SIZE,
        _no_fixture,
        _transcript_capture(_worktrees_text(), CLI_SIZE, "lpui plan worktree"),
        "Terminal transcript of lpui plan worktree list, print, and add showing the registered lane checkouts, the git worktree command for a new lane, and the registration result.",
    ),
    "lpui-coordination": Scene(
        SIZE,
        build_coordination_fixture,
        capture_coordination,
        "lazyplan plan tree with title-only task rows and attention markers on a blocked task, aging work, and a done row with an open criterion, plus a failing pull-request check.",
    ),
    "lpui-collaboration": Scene(
        SIZE,
        build_coordination_fixture,
        capture_collaboration,
        "Task overview showing an active claim, two review comments, and a handoff note.",
    ),
    "lpui-flow-health": Scene(
        TRANSCRIPT_SIZE,
        _no_fixture,
        _transcript_capture(_flow_health_text(), TRANSCRIPT_SIZE, "lpui stats — flow health"),
        "Terminal transcript of lpui stats showing WIP, cycle time, throughput, aging, stale todos, reopened work, claims, blocked tasks, and porcelain metric rows.",
    ),
    "lpui-trace": Scene(
        TRANSCRIPT_SIZE,
        _no_fixture,
        _transcript_capture(_trace_text(), TRANSCRIPT_SIZE, "lpui trace + lint"),
        "Terminal transcript of lpui trace and lpui lint --strict showing criterion-to-task-to-commit-to-PR evidence and a missing proving task finding.",
    ),
    "lpui-mcp": Scene(
        TRANSCRIPT_SIZE,
        _no_fixture,
        _transcript_capture(_mcp_text(), TRANSCRIPT_SIZE, "lpui mcp — stdio session"),
        "Terminal transcript of an lpui mcp stdio session showing initialize, tools/list, and a brief tools/call response.",
    ),
    "lpui-share-sync": Scene(
        TRANSCRIPT_SIZE,
        _no_fixture,
        _transcript_capture(_share_sync_text(), TRANSCRIPT_SIZE, "lpui comment + share + sync"),
        "Terminal transcript showing a comment with an @mention, a read-only HTML share, and a dry-run sync with a conflict.",
    ),
    "lpui-gates": Scene(
        TRANSCRIPT_SIZE,
        _no_fixture,
        _transcript_capture(_gates_text(), TRANSCRIPT_SIZE, "lpui task finish — completion gates"),
        "Terminal transcript showing task finish blocked by failing checks, then completed with an override note and gate state.",
    ),
    "lpui-imports": Scene(
        TRANSCRIPT_SIZE,
        _no_fixture,
        _transcript_capture(_imports_text(), TRANSCRIPT_SIZE, "lpui issue import"),
        "Terminal transcript showing a GitHub issue import dry-run and a Linear import with source refs in plan show.",
    ),
}


def patch_svg(path: Path) -> None:
    """Preserve leading spaces: librsvg collapses them in Rich's text runs."""
    text = path.read_text(encoding="utf-8")
    text = text.replace("<text ", '<text xml:space="preserve" ')
    path.write_text(text, encoding="utf-8", newline="\n")


def write_webp(png: Path) -> None:
    """Write the WebP sibling of a rendered PNG."""
    subprocess.run(
        ["magick", str(png), "-quality", "82", str(png.with_suffix(".webp"))],
        check=True,
    )


def convert(svg: Path, png: Path) -> None:
    if shutil.which("magick") is None:
        raise SystemExit("error: ImageMagick 7 (magick) is required")
    # One process writes both outputs: the PNG is the stripped render and the
    # WebP is encoded from the same in-memory image, so the bytes match the
    # previous two-command pipeline while saving a spawn and a decode.
    subprocess.run(
        [
            "magick",
            str(svg),
            "-strip",
            "-write",
            str(png),
            "-quality",
            "82",
            str(png.with_suffix(".webp")),
        ],
        check=True,
    )


def dimensions(png: Path) -> str:
    """Read the PNG IHDR instead of spawning another process."""
    header = png.read_bytes()[:24]
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit(f"error: {png} is not a PNG")
    width, height = struct.unpack(">II", header[16:24])
    return f"{width}x{height}"


def shown(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def build_og(screenshot: Path, target: Path) -> None:
    """Compose a deterministic 1200x630 social card from the coordination shot."""
    if not screenshot.is_file():
        raise SystemExit(f"error: missing OG source {screenshot}")
    base = target.with_suffix(".base.png")
    try:
        subprocess.run(
            [
                "magick",
                "-size",
                "1200x630",
                "xc:#09090b",
                "-fill",
                "rgba(59,130,246,0.16)",
                "-draw",
                "circle 1040,80 1240,80",
                "-fill",
                "rgba(34,211,238,0.10)",
                "-draw",
                "circle 120,600 260,600",
                "-font",
                "Cantarell-Extra-Bold",
                "-pointsize",
                "78",
                "-fill",
                "#fafafa",
                "-annotate",
                "+64+150",
                "lazyplan.",
                "-font",
                "Cantarell-Bold",
                "-pointsize",
                "34",
                "-fill",
                "#d4d4d8",
                "-annotate",
                "+68+220",
                "Plan it. Dispatch it.",
                "-annotate",
                "+68+264",
                "Prove it.",
                "-font",
                "Cantarell",
                "-pointsize",
                "23",
                "-fill",
                "#22d3ee",
                "-annotate",
                "+68+350",
                "First run · The plan · Lanes",
                "-annotate",
                "+68+382",
                "Worktrees · Proof",
                "-font",
                "Cantarell",
                "-pointsize",
                "20",
                "-fill",
                "#a1a1aa",
                "-annotate",
                "+68+560",
                "fluxion-dev.github.io/lazyplan",
                str(base),
            ],
            check=True,
        )
        subprocess.run(
            [
                "magick",
                str(base),
                "(",
                str(screenshot),
                "-resize",
                "740x",
                "-bordercolor",
                "#27272a",
                "-border",
                "4",
                ")",
                "-geometry",
                "+420+170",
                "-composite",
                "-strip",
                "-depth",
                "8",
                str(target),
            ],
            check=True,
        )
    finally:
        base.unlink(missing_ok=True)


def _framed(path: Path, size: str) -> list[str]:
    """Return the ImageMagick tokens for one framed, letterboxed screenshot."""
    return [
        "(",
        str(path),
        "-resize",
        size,
        "-background",
        "#0b0b12",
        "-gravity",
        "center",
        "-extent",
        size,
        "-bordercolor",
        "#27272a",
        "-border",
        "2",
        ")",
    ]


def build_cinematic_hero(plan: Path, dispatch: Path, proof: Path, target: Path) -> None:
    """Compose the 2400x1200 hero: plan, dispatch, and proof side by side."""
    for path in (plan, dispatch, proof):
        if not path.is_file():
            raise SystemExit(f"error: missing hero source {path}")
    subprocess.run(
        [
            "magick",
            "-size",
            "2400x1200",
            "gradient:#0b0b12-#050507",
            *_framed(plan, "1440x812"),
            "-gravity",
            "northwest",
            "-geometry",
            "+60+194",
            "-composite",
            *_framed(dispatch, "820x360"),
            "-gravity",
            "northwest",
            "-geometry",
            "+1540+100",
            "-composite",
            *_framed(proof, "820x462"),
            "-gravity",
            "northwest",
            "-geometry",
            "+1540+560",
            "-composite",
            "-fill",
            "#f59e0b",
            "-draw",
            "rectangle 60,88 2340,90",
            "-strip",
            "-depth",
            "8",
            str(target),
        ],
        check=True,
    )
    write_webp(target)


def run(out_dir: Path, only: list[str], keep_svg: Path | None, make_og: bool) -> None:
    os.environ.setdefault("LAZYPLAN_NO_SPINNER", "1")
    os.environ.setdefault("LAZYPLAN_NO_SETUP", "1")
    os.environ.setdefault("LAZYPLAN_NO_UPDATE_CHECK", "1")
    names = only or list(SCENES)
    if not only and out_dir == DEFAULT_OUT.resolve():
        names = [name for name in names if name in SITE_SCENES]
    unknown = [name for name in names if name not in SCENES]
    if unknown:
        raise SystemExit(f"error: unknown scene(s): {', '.join(unknown)}")
    if keep_svg is not None and len(names) != 1:
        raise SystemExit("error: --keep-svg needs exactly one --only scene")

    real_snapshot = metrics.snapshot

    def frozen_snapshot(store: Store, now: float | None = None, **kwargs: object):
        return real_snapshot(store, now=FIXED_NOW, **kwargs)

    with (
        mock.patch("lazyplan.store.base.time.time", return_value=STAMP),
        mock.patch("lazyplan.services.metrics.snapshot", side_effect=frozen_snapshot),
    ):
        shutil.rmtree(FIXTURE_ROOT, ignore_errors=True)
        FIXTURE_ROOT.mkdir(parents=True, exist_ok=True)
        out_dir.mkdir(parents=True, exist_ok=True)
        pending: list[tuple[Path, Future[None]]] = []
        workers = min(4, os.cpu_count() or 1)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for name in names:
                scene = SCENES[name]
                scene_dir = FIXTURE_ROOT / name
                scene_dir.mkdir(parents=True, exist_ok=True)
                store = scene.build(scene_dir)
                svg = scene_dir / f"{name}.svg"
                asyncio.run(scene.capture(store, svg))
                patch_svg(svg)
                png = out_dir / f"{name}.png"
                # Conversion is a separate process; overlap it with the next
                # capture. The bytes are identical to converting inline.
                pending.append((png, pool.submit(convert, svg, png)))
                if keep_svg is not None:
                    shutil.copyfile(svg, keep_svg)
            for png, future in pending:
                future.result()
                print(f"wrote {shown(png)} ({dimensions(png)})")
                print(f"wrote {shown(png.with_suffix('.webp'))}")
        hero_sources = {
            "lpui-control-room",
            "lpui-dispatch",
            "lpui-source-trail",
        }
        if hero_sources <= set(names):
            hero = out_dir / "lpui-hero.png"
            build_cinematic_hero(
                out_dir / "lpui-control-room.png",
                out_dir / "lpui-dispatch.png",
                out_dir / "lpui-source-trail.png",
                hero,
            )
            print(f"wrote {shown(hero)} ({dimensions(hero)})")
            print(f"wrote {shown(hero.with_suffix('.webp'))}")
        if make_og and "lpui-coordination" in set(names):
            og = out_dir / "og-lpui-and-agent.png"
            build_og(out_dir / "lpui-coordination.png", og)
            print(f"wrote {shown(og)} ({dimensions(og)})")


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
        choices=sorted(SCENES),
        help="generate only this scene (repeatable)",
    )
    parser.add_argument("--keep-svg", type=Path, help="copy the intermediate SVG here")
    parser.add_argument("--no-og", action="store_true", help="skip the social card")
    args = parser.parse_args(argv)
    run(args.out.resolve(), args.only, args.keep_svg, not args.no_og)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
