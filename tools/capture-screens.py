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
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from rich.text import Text  # noqa: E402
from textual.app import App, ComposeResult  # noqa: E402
from textual.widgets import Static, Tree  # noqa: E402

from lazyplan import services  # noqa: E402
from lazyplan.models import Status  # noqa: E402
from lazyplan.store import Store  # noqa: E402
from lazyplan.tui import create_app  # noqa: E402
from lazyplan.tui.screens import DetailScreen, PaletteScreen  # noqa: E402
from lazyplan.tui.screens.source import SourceScreen  # noqa: E402

SIZE = (130, 35)
TRANSCRIPT_SIZE = (120, 22)
DEFAULT_OUT = ROOT / "site" / "public" / "screens"
DATE = "2026-10-01T09:00:00+00:00"
AUTHOR = "Ada Lovelace"
EMAIL = "ada@acme.dev"
REMOTE = "git@github.com:acme/web.git"
STAMP = 1767261600.0  # 2026-01-01 09:00 UTC, safely older than the attention window

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
    plan = store.add_plan("Ship the source trail")
    milestone = store.add_milestone(plan.id, "Read diffs in place")
    task = store.add_task(milestone.id, "Render unified diffs")
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
        "Leases, handoffs, and the Attention view.",
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


def build_search_fixture(tmp: Path) -> Store:
    """A small plan with enough rows to show marks and bulk context."""
    store = Store(str(tmp / "plan.db"))
    plan = store.add_plan(
        "Search and bulk edit",
        "Find the row by what it says, mark several, and edit once.",
        goal="Keep large journals navigable.",
    )
    milestone = store.add_milestone(plan.id, "Bulk workflow", "Marks and undo.")
    rows = (
        ("Find the release notes", "Search descriptions and notes."),
        ("Mark the queue rows", "Select several tasks."),
        ("Bulk move the release set", "Apply one status change."),
        ("Release the stale leases", "Report conflicts per row."),
        ("Keep delete single-row", "Undo cannot recreate a subtree."),
    )
    for title, desc in rows:
        store.add_task(milestone.id, title, desc)
    with mock.patch("lazyplan.store.base.time.time", return_value=STAMP):
        services.set_status(store, "task", 1, Status.DOING, actor="Ada")
        services.set_status(store, "task", 2, Status.DOING, actor="Ada")
    store.add_note("task", 1, "Search covers descriptions, notes, and comments.", actor="Ada")
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


def _expand_all(tree: Tree[object]) -> None:
    for plan in tree.root.children:
        plan.expand()
        for milestone in plan.children:
            milestone.expand()


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
        tree.focus()
        await pilot.pause()
        tree.select_node(feature_node.children[0])
        await pilot.pause()
        app.save_screenshot(str(target))


async def capture_coordination(store: Store, target: Path) -> None:
    app = create_app(str(store.path))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        app.source_filter = "attention"
        app.refresh_all("attention")
        await pilot.pause()
        tree = app.query_one("#tree", Tree)
        _expand_all(tree)
        tree.focus()
        tasks = _nodes(tree, "task")
        if tasks:
            tree.select_node(tasks[0])
        await pilot.pause()
        app.save_screenshot(str(target))


async def capture_collaboration(store: Store, target: Path) -> None:
    task_id = _task_id(store, "Claim the release queue")
    app = create_app(str(store.path))
    async with app.run_test(size=SIZE) as pilot:
        app.push_screen(DetailScreen(store, "task", task_id))
        await pilot.pause()
        app.save_screenshot(str(target))


async def capture_search(store: Store, target: Path) -> None:
    app = create_app(str(store.path))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        app.marked = {("task", 1), ("task", 2), ("task", 3)}
        app.selected = ("task", 2)
        app.refresh_all("marked 3")
        await pilot.pause()
        tree = app.query_one("#tree", Tree)
        _expand_all(tree)
        tree.focus()
        tasks = _nodes(tree, "task")
        if tasks:
            tree.select_node(tasks[1])
        await pilot.pause()
        app.save_screenshot(str(target))


async def capture_palette(store: Store, target: Path) -> None:
    app = create_app(str(store.path))
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        app.push_screen(PaletteScreen({}))
        await pilot.pause()
        app.screen.query_one("#palette-input").value = "bulk"
        await pilot.pause()
        app.save_screenshot(str(target))


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
    "lpui-source-trail": Scene(
        SIZE,
        build_source_fixture,
        capture_source,
        "lazyplan source trail for a task showing a repository, commits, changed files, a merged pull request, and a unified diff.",
    ),
    "lpui-coordination": Scene(
        SIZE,
        build_coordination_fixture,
        capture_coordination,
        "lazyplan plan tree filtered to Attention, showing an active claim, an expired claim, a blocked task, aging work, a done row with an open criterion, and a red PR check.",
    ),
    "lpui-collaboration": Scene(
        SIZE,
        build_coordination_fixture,
        capture_collaboration,
        "lazyplan task detail page showing an active claim, two review comments, and a handoff note.",
    ),
    "lpui-search-bulk": Scene(
        SIZE,
        build_search_fixture,
        capture_search,
        "lazyplan plan tree with three marked tasks showing checkmarks and a marked 3 count in the status line.",
    ),
    "lpui-bulk-palette": Scene(
        SIZE,
        build_search_fixture,
        capture_palette,
        "lazyplan command palette filtered to bulk commands: mark, move to doing, move to done, block, release claims, and undo.",
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


def convert(svg: Path, png: Path) -> None:
    if shutil.which("magick") is None:
        raise SystemExit("error: ImageMagick 7 (magick) is required")
    subprocess.run(["magick", str(svg), "-strip", str(png)], check=True)
    subprocess.run(
        ["magick", str(png), "-quality", "82", str(png.with_suffix(".webp"))], check=True
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
                "One plan. You steer.",
                "-annotate",
                "+68+264",
                "Your agent helps.",
                "-font",
                "Cantarell",
                "-pointsize",
                "23",
                "-fill",
                "#22d3ee",
                "-annotate",
                "+68+350",
                "Coordination · Flow health",
                "-annotate",
                "+68+382",
                "Collaboration · Proof",
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


def build_hero(coordination: Path, mcp: Path, gates: Path, target: Path) -> None:
    """Compose the 1600x760 hero: plan on the left, agent surfaces on the right."""
    for path in (coordination, mcp, gates):
        if not path.is_file():
            raise SystemExit(f"error: missing hero source {path}")
    subprocess.run(
        [
            "magick",
            "-size",
            "1600x760",
            "xc:#09090b",
            "(",
            str(coordination),
            "-resize",
            "980x",
            "-bordercolor",
            "#27272a",
            "-border",
            "2",
            ")",
            "-geometry",
            "+20+102",
            "-composite",
            "(",
            str(mcp),
            "-resize",
            "560x",
            "-bordercolor",
            "#27272a",
            "-border",
            "2",
            ")",
            "-geometry",
            "+1020+104",
            "-composite",
            "(",
            str(gates),
            "-resize",
            "560x",
            "-bordercolor",
            "#27272a",
            "-border",
            "2",
            ")",
            "-geometry",
            "+1020+430",
            "-composite",
            "-strip",
            "-depth",
            "8",
            str(target),
        ],
        check=True,
    )
    subprocess.run(
        ["magick", str(target), "-quality", "82", str(target.with_suffix(".webp"))],
        check=True,
    )


def run(out_dir: Path, only: list[str], keep_svg: Path | None, make_og: bool) -> None:
    os.environ.setdefault("LAZYPLAN_NO_SPINNER", "1")
    names = only or list(SCENES)
    unknown = [name for name in names if name not in SCENES]
    if unknown:
        raise SystemExit(f"error: unknown scene(s): {', '.join(unknown)}")
    if keep_svg is not None and len(names) != 1:
        raise SystemExit("error: --keep-svg needs exactly one --only scene")

    with tempfile.TemporaryDirectory(prefix="lpui-shot-") as tmp:
        for name in names:
            scene = SCENES[name]
            scene_dir = Path(tmp) / name
            scene_dir.mkdir(parents=True, exist_ok=True)
            store = scene.build(scene_dir)
            svg = Path(tmp) / f"{name}.svg"
            asyncio.run(scene.capture(store, svg))
            patch_svg(svg)
            png = out_dir / f"{name}.png"
            out_dir.mkdir(parents=True, exist_ok=True)
            convert(svg, png)
            if keep_svg is not None:
                shutil.copyfile(svg, keep_svg)
            print(f"wrote {shown(png)} ({dimensions(png)})")
            print(f"wrote {shown(png.with_suffix('.webp'))}")
        if make_og and {"lpui-coordination", "lpui-mcp", "lpui-gates"} <= set(names):
            hero = out_dir / "lpui-and-agent.png"
            build_hero(
                out_dir / "lpui-coordination.png",
                out_dir / "lpui-mcp.png",
                out_dir / "lpui-gates.png",
                hero,
            )
            print(f"wrote {shown(hero)} ({dimensions(hero)})")
            print(f"wrote {shown(hero.with_suffix('.webp'))}")
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
