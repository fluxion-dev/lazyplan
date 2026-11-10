"""Unified-diff parsing and the small diff read cache."""

from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from lazyplan.infrastructure.vcs import DiffRead, detect_backend

DIFF_CACHE_LIMIT = 16

_HUNK_RE = re.compile(
    r"^@@ -(?P<old>\d+)(?:,(?P<old_count>\d+))?"
    r" \+(?P<new>\d+)(?:,(?P<new_count>\d+))? @@ ?(?P<section>.*)$"
)
_GIT_FILE_RE = re.compile(r"^diff --git a/(?P<old>.+?) b/(?P<new>.+)$")


@dataclass(frozen=True)
class DiffLine:
    """One unified-diff line with its old and new line numbers."""

    kind: str  # add | remove | context | meta
    text: str = ""
    old_no: int | None = None
    new_no: int | None = None


@dataclass(frozen=True)
class DiffHunk:
    """One `@@` hunk and its numbered lines."""

    header: str
    old_start: int = 0
    old_count: int = 0
    new_start: int = 0
    new_count: int = 0
    lines: tuple[DiffLine, ...] = ()


@dataclass(frozen=True)
class DiffFile:
    """One file section of a unified diff."""

    old_path: str = ""
    new_path: str = ""
    header: tuple[str, ...] = ()
    hunks: tuple[DiffHunk, ...] = ()
    binary: bool = False

    @property
    def path(self) -> str:
        """Display path: the new path, falling back to the old one."""
        return self.new_path or self.old_path


def _clean_diff_path(raw: str) -> str:
    """Path from a `---`/`+++` header, with /dev/null becoming empty."""
    text = raw.split("\t", 1)[0].strip()
    if text == "/dev/null":
        return ""
    if text.startswith(("a/", "b/")):
        return text[2:]
    return text


def _build_hunk(header: str, body: list[str]) -> DiffHunk:
    """Turn one hunk header and its raw body into numbered lines."""
    match = _HUNK_RE.match(header)
    if match is None:
        return DiffHunk(header=header, lines=(DiffLine("meta", header),))
    old_no = int(match.group("old"))
    new_no = int(match.group("new"))
    lines: list[DiffLine] = []
    for raw in body:
        if raw.startswith("\\"):
            lines.append(DiffLine("meta", raw[1:].strip()))
        elif raw.startswith("+"):
            lines.append(DiffLine("add", raw[1:], None, new_no))
            new_no += 1
        elif raw.startswith("-"):
            lines.append(DiffLine("remove", raw[1:], old_no, None))
            old_no += 1
        elif raw.startswith(" "):
            lines.append(DiffLine("context", raw[1:], old_no, new_no))
            old_no += 1
            new_no += 1
        else:
            lines.append(DiffLine("meta", raw))
    return DiffHunk(
        header=header,
        old_start=int(match.group("old")),
        old_count=int(match.group("old_count") or 1),
        new_start=int(match.group("new")),
        new_count=int(match.group("new_count") or 1),
        lines=tuple(lines),
    )


def _parse_file_chunk(lines: list[str]) -> DiffFile:
    """Parse one `diff --git` chunk into file metadata and hunks."""
    old_path = ""
    new_path = ""
    header: list[str] = []
    hunks: list[DiffHunk] = []
    binary = False
    hunk_header = ""
    hunk_body: list[str] = []
    for raw in lines:
        if hunk_header:
            if raw.startswith(("+", "-", " ", "\\")):
                hunk_body.append(raw)
                continue
            hunks.append(_build_hunk(hunk_header, hunk_body))
            hunk_header = ""
            hunk_body = []
        if raw.startswith("diff --git "):
            match = _GIT_FILE_RE.match(raw)
            if match is not None:
                old_path = _clean_diff_path(match.group("old"))
                new_path = _clean_diff_path(match.group("new"))
            header.append(raw)
        elif raw.startswith(("Binary files ", "GIT binary patch")):
            binary = True
            header.append(raw)
        elif raw.startswith("--- "):
            old_path = _clean_diff_path(raw[4:])
            header.append(raw)
        elif raw.startswith("+++ "):
            new_path = _clean_diff_path(raw[4:])
            header.append(raw)
        elif _HUNK_RE.match(raw):
            hunk_header = raw
        else:
            header.append(raw)
    if hunk_header:
        hunks.append(_build_hunk(hunk_header, hunk_body))
    return DiffFile(
        old_path=old_path,
        new_path=new_path,
        header=tuple(header),
        hunks=tuple(hunks),
        binary=binary,
    )


def parse_patch(text: str) -> tuple[DiffFile, ...]:
    """Parse a unified diff into files, hunks, and numbered lines."""
    chunks: list[list[str]] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.startswith("diff --git "):
            if current:
                chunks.append(current)
            current = [line]
        elif current:
            current.append(line)
    if current:
        chunks.append(current)
    return tuple(_parse_file_chunk(chunk) for chunk in chunks)


_diff_cache: OrderedDict[tuple[str, str, str], DiffRead] = OrderedDict()


def _cache_key(repo: str, sha: str, path: str) -> tuple[str, str, str]:
    root = str(Path(repo).expanduser().resolve()) if repo.strip() else ""
    return (root, sha.strip(), path.strip())


def read_diff(repo: str, sha: str, path: str = "") -> DiffRead:
    """Read a bounded diff through a small LRU cache keyed by repo, sha, path."""
    key = _cache_key(repo, sha, path)
    hit = _diff_cache.get(key)
    if hit is not None:
        _diff_cache.move_to_end(key)
        return hit
    result = _read_diff_uncached(repo, sha, path)
    _diff_cache[key] = result
    while len(_diff_cache) > DIFF_CACHE_LIMIT:
        _diff_cache.popitem(last=False)
    return result


def _read_diff_uncached(repo: str, sha: str, path: str) -> DiffRead:
    """Read one diff without touching the cache."""
    if not repo.strip():
        return DiffRead(state="error", detail="no checkout linked")
    backend, root = detect_backend(repo)
    if backend is None or root is None:
        return DiffRead(state="error", detail="not a git checkout")
    return backend.diff(root, sha, path)


def clear_diff_cache() -> None:
    """Drop every cached diff (tests and explicit refresh)."""
    _diff_cache.clear()
