"""VCS integration: open layer for linking commits to P/S/T.

Only git is implemented now; other systems plug in as new backends.
Stdlib only (subprocess), offline, fast timeouts.
"""

from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommitInfo:
    """Identity of one commit: SHA plus display metadata."""

    sha: str
    subject: str = ""
    author: str = ""
    timestamp: int = 0
    repo_root: str = ""


class VCSBackend(ABC):
    """Pluggable version-control backend. Git is the only one for now."""

    name: str = ""

    @abstractmethod
    def detect(self, cwd: str | Path = ".") -> Path | None:
        """Repo root for cwd, or None when this backend does not apply."""
        raise NotImplementedError

    def is_available(self, cwd: str | Path = ".") -> bool:
        """True when commit linking should be enabled here."""
        return self.detect(cwd) is not None

    @abstractmethod
    def head(self, root: str | Path) -> str | None:
        """Current HEAD SHA, or None (no commits / not a repo)."""
        raise NotImplementedError

    @abstractmethod
    def show(self, root: str | Path, sha: str) -> CommitInfo | None:
        """Metadata for sha, or None when unresolvable."""
        raise NotImplementedError


def _run_git(root: str | Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    """Run git in root; None on missing binary or timeout."""
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return None


class GitBackend(VCSBackend):
    """Git implementation of the VCS layer."""

    name = "git"

    def detect(self, cwd: str | Path = ".") -> Path | None:
        """Enclosing git root, or None. Requires a working git CLI."""
        from .repo import find_repo_root

        root = find_repo_root(cwd)
        if root is None:
            return None
        out = _run_git(root, "rev-parse", "--git-dir")
        if out is None or out.returncode != 0:
            return None
        return root

    def head(self, root: str | Path) -> str | None:
        """HEAD SHA, or None when there is no commit yet."""
        out = _run_git(root, "rev-parse", "HEAD")
        if out is None or out.returncode != 0:
            return None
        sha = out.stdout.strip()
        return sha if sha else None

    def show(self, root: str | Path, sha: str) -> CommitInfo | None:
        """Resolve sha to full CommitInfo; None when unknown."""
        ref = sha.strip()
        if not ref:
            return None
        full = _run_git(root, "rev-parse", "--verify", f"{ref}^{{commit}}")
        if full is None or full.returncode != 0:
            return None
        resolved = full.stdout.strip()
        if not resolved:
            return None
        out = _run_git(root, "log", "-1", "--format=%s%n%an%n%at", resolved)
        subject, author, ts = "", "", 0
        if out is not None and out.returncode == 0:
            lines = out.stdout.splitlines()
            if len(lines) >= 1:
                subject = lines[0].strip()
            if len(lines) >= 2:
                author = lines[1].strip()
            if len(lines) >= 3:
                try:
                    ts = int(lines[2].strip())
                except ValueError:
                    ts = 0
        return CommitInfo(
            sha=resolved,
            subject=subject,
            author=author,
            timestamp=ts,
            repo_root=str(Path(root).resolve()),
        )


_BACKENDS: list[VCSBackend] = [GitBackend()]


def backends() -> list[VCSBackend]:
    """Registered backends; append new ones here to support more VCSs."""
    return list(_BACKENDS)


def detect_backend(cwd: str | Path = ".") -> tuple[VCSBackend | None, Path | None]:
    """First backend claiming cwd, else (None, None). Git-only for now."""
    for backend in _BACKENDS:
        root = backend.detect(cwd)
        if root is not None:
            return backend, root
    return None, None


def current_head(cwd: str | Path = ".") -> tuple[VCSBackend | None, CommitInfo | None]:
    """HEAD commit for cwd's repo, else (None, None) outside a VCS."""
    backend, root = detect_backend(cwd)
    if backend is None or root is None:
        return None, None
    sha = backend.head(root)
    if sha is None:
        return backend, None
    return backend, backend.show(root, sha)
