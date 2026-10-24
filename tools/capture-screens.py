#!/usr/bin/env python3
"""Regenerate the site's TUI screenshots from a deterministic fixture.

Usage:
  .venv/bin/python tools/capture-screens.py [--out DIR] [--keep-svg PATH]

Builds a throwaway git repo and plan database, opens the real source-trail
screen at 130x35, exports the SVG, then converts it to PNG and WebP for the
site. The fixture uses fixed commit dates and a fictional `acme/web` remote, so
two runs produce byte-identical images and no personal data appears.

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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from lazyplan.source_screen import SourceScreen  # noqa: E402
from lazyplan.store import Store  # noqa: E402
from lazyplan.tui import create_app  # noqa: E402

SIZE = (130, 35)
NAME = "lpui-source-trail"
DEFAULT_OUT = ROOT / "site" / "public" / "screens"
DATE = "2026-10-01T09:00:00+00:00"
AUTHOR = "Ada Lovelace"
EMAIL = "ada@acme.dev"
REMOTE = "git@github.com:acme/web.git"

BASE_FILES = {
    "app/source.py": "def trail():\n    return []\n",
    "app/diff.py": "def render():\n    return ''\n",
    "app/link.py": "def link():\n    return None\n",
    "docs/usage.md": "# usage\n\nPress g.\n",
}
FEATURE_FILES = {
    "app/source.py": (
        "def trail(repo):\n"
        "    commits = repo.commits()\n"
        "    return commits\n"
    ),
    "app/diff.py": (
        "def render(diff):\n"
        "    return [line for line in diff]\n"
    ),
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
        text=True,
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
        path.write_text(text)


def commit(repo: Path, message: str, files: dict[str, str]) -> str:
    write_files(repo, files)
    git(repo, "add", ".")
    git(repo, "commit", "-qm", message, env=commit_env())
    return git(repo, "rev-parse", "HEAD").strip()


def build_fixture(tmp: Path) -> tuple[Store, int]:
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
    store.add_repo_link(
        "task", task.id, str(repo), REMOTE, branch="main", base_sha=base
    )
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
    return store, task.id


async def capture(store: Store, task_id: int, target: Path) -> None:
    app = create_app(str(store.path))
    async with app.run_test(size=SIZE) as pilot:
        app.push_screen(SourceScreen(store, "task", task_id))
        await pilot.pause()
        tree = app.screen.query_one("#source-tree")
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


def patch_svg(path: Path) -> None:
    """Preserve leading spaces: librsvg collapses them in Rich's text runs."""
    text = path.read_text()
    text = text.replace("<text ", '<text xml:space="preserve" ')
    path.write_text(text)


def convert(svg: Path, png: Path) -> None:
    if shutil.which("magick") is None:
        raise SystemExit("error: ImageMagick 7 (magick) is required")
    subprocess.run(["magick", str(svg), "-strip", str(png)], check=True)
    subprocess.run(["magick", str(png), "-quality", "82", str(png.with_suffix(".webp"))], check=True)


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


def run(out_dir: Path, keep_svg: Path | None) -> None:
    with tempfile.TemporaryDirectory(prefix="lpui-shot-") as tmp:
        store, task_id = build_fixture(Path(tmp))
        svg = Path(tmp) / f"{NAME}.svg"
        asyncio.run(capture(store, task_id, svg))
        patch_svg(svg)
        png = out_dir / f"{NAME}.png"
        out_dir.mkdir(parents=True, exist_ok=True)
        convert(svg, png)
        if keep_svg is not None:
            shutil.copyfile(svg, keep_svg)
        print(f"wrote {shown(png)} ({dimensions(png)})")
        print(f"wrote {shown(png.with_suffix('.webp'))}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"output directory (default: {DEFAULT_OUT.relative_to(ROOT)})",
    )
    parser.add_argument("--keep-svg", type=Path, help="copy the intermediate SVG here")
    args = parser.parse_args(argv)
    run(args.out.resolve(), args.keep_svg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
