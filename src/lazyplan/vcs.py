"""VCS integration: read-only layer for linking commits to P/S/T.

lazyplan never creates branches, worktrees, commits, pushes, or merges.
Only git is implemented now; other systems plug in as new backends.
Stdlib only (subprocess), offline, fast timeouts.
"""

from __future__ import annotations

import subprocess
import urllib.parse
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommitInfo:
    """Identity of one commit: SHA plus display and provenance metadata."""

    sha: str
    subject: str = ""
    author: str = ""
    timestamp: int = 0
    repo_root: str = ""
    body: str = ""
    files: tuple[str, ...] = ()
    parents: tuple[str, ...] = ()
    branch: str = ""


@dataclass(frozen=True)
class RemoteInfo:
    """One named remote and its fetch/push URLs."""

    name: str
    fetch_url: str = ""
    push_url: str = ""


@dataclass(frozen=True)
class RepoStatus:
    """Working-tree state for one checkout."""

    branch: str = ""
    head: str = ""
    dirty: bool = False
    ahead: int = 0
    behind: int = 0
    upstream: str = ""
    detached: bool = False


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

    @abstractmethod
    def branch(self, root: str | Path) -> str | None:
        """Current branch name, or None on a detached HEAD or outside a repo."""
        raise NotImplementedError

    @abstractmethod
    def status(self, root: str | Path) -> RepoStatus:
        """Branch, dirty tree, and ahead/behind state for one checkout."""
        raise NotImplementedError

    @abstractmethod
    def log(
        self,
        root: str | Path,
        rev_range: str = "",
        limit: int = 50,
        since: str = "",
    ) -> list[CommitInfo]:
        """Commits for a range (default HEAD), newest first."""
        raise NotImplementedError

    @abstractmethod
    def remotes(self, root: str | Path) -> list[RemoteInfo]:
        """Named remotes for one checkout, sorted by name."""
        raise NotImplementedError

    @abstractmethod
    def branch_exists(self, root: str | Path, name: str) -> bool:
        """True when a local branch with this name exists."""
        raise NotImplementedError

    @abstractmethod
    def merge_base(self, root: str | Path, ref_a: str, ref_b: str) -> str | None:
        """Best common ancestor of two refs, or None when unrelated."""
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

    # Record separator + field separator keep subjects with newlines safe.
    # Fields: sha, subject, body, author, timestamp, parents.
    _LOG_FORMAT = "%H%x1f%s%x1f%b%x1f%an%x1f%at%x1f%P%x1e"

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

    def branch(self, root: str | Path) -> str | None:
        """Current branch name; None on a detached HEAD."""
        out = _run_git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
        if out is None or out.returncode != 0:
            return None
        name = out.stdout.strip()
        return name or None

    def status(self, root: str | Path) -> RepoStatus:
        """Branch, dirty tree, and ahead/behind counts for one checkout."""
        head = self.head(root) or ""
        branch = self.branch(root)
        dirty = self._dirty(root)
        upstream, ahead, behind = self._tracking(root)
        return RepoStatus(
            branch=branch or "",
            head=head,
            dirty=dirty,
            ahead=ahead,
            behind=behind,
            upstream=upstream,
            detached=branch is None and bool(head),
        )

    def log(
        self,
        root: str | Path,
        rev_range: str = "",
        limit: int = 50,
        since: str = "",
    ) -> list[CommitInfo]:
        """Commits for rev_range (default HEAD), newest first."""
        if rev_range.startswith("-"):
            return []
        args = ["log", f"-n{max(1, min(limit, 1000))}", f"--format={self._LOG_FORMAT}"]
        if since:
            args.append(f"--since={since}")
        if rev_range:
            args.append(rev_range)
        out = _run_git(root, *args)
        if out is None or out.returncode != 0:
            return []
        branch = self.branch(root) or ""
        return self._parse_log(out.stdout, root, branch=branch)

    def remotes(self, root: str | Path) -> list[RemoteInfo]:
        """Named remotes with fetch and push URLs, sorted by name."""
        out = _run_git(root, "remote", "-v")
        if out is None or out.returncode != 0:
            return []
        by_name: dict[str, dict[str, str]] = {}
        for line in out.stdout.splitlines():
            parts = line.split()
            if len(parts) < 3:
                continue
            name, url, direction = parts[0], parts[1], parts[2]
            slot = by_name.setdefault(name, {"fetch": "", "push": ""})
            if direction == "(fetch)" and not slot["fetch"]:
                slot["fetch"] = url
            elif direction == "(push)" and not slot["push"]:
                slot["push"] = url
        return [
            RemoteInfo(name=name, fetch_url=slot["fetch"], push_url=slot["push"])
            for name, slot in sorted(by_name.items())
        ]

    def branch_exists(self, root: str | Path, name: str) -> bool:
        """True when a local branch with this name exists."""
        out = _run_git(root, "show-ref", "--verify", "--quiet", f"refs/heads/{name.strip()}")
        return bool(out is not None and out.returncode == 0)

    def merge_base(self, root: str | Path, ref_a: str, ref_b: str) -> str | None:
        """Best common ancestor of two refs, or None when unrelated."""
        out = _run_git(root, "merge-base", ref_a, ref_b)
        if out is None or out.returncode != 0:
            return None
        sha = out.stdout.strip()
        return sha or None

    @staticmethod
    def _dirty(root: str | Path) -> bool:
        """True when tracked or untracked files differ from HEAD."""
        out = _run_git(root, "status", "--porcelain")
        return bool(out is not None and out.returncode == 0 and out.stdout.strip())

    def _tracking(self, root: str | Path) -> tuple[str, int, int]:
        """Upstream name plus (ahead, behind); empty/zero when untracked."""
        ref = _run_git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
        if ref is None or ref.returncode != 0:
            return "", 0, 0
        upstream = ref.stdout.strip()
        if not upstream:
            return "", 0, 0
        counts = _run_git(root, "rev-list", "--left-right", "--count", f"{upstream}...HEAD")
        if counts is None or counts.returncode != 0:
            return upstream, 0, 0
        parts = counts.stdout.split()
        if len(parts) != 2:
            return upstream, 0, 0
        try:
            behind, ahead = int(parts[0]), int(parts[1])
        except ValueError:
            return upstream, 0, 0
        return upstream, ahead, behind

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
        out = _run_git(root, "log", "-1", f"--format={self._LOG_FORMAT}", resolved)
        if out is None or out.returncode != 0:
            return None
        branch = self.branch(root) or ""
        commits = self._parse_log(out.stdout, root, branch=branch)
        if not commits:
            return None
        info = commits[0]
        return CommitInfo(
            sha=info.sha,
            subject=info.subject,
            author=info.author,
            timestamp=info.timestamp,
            repo_root=info.repo_root,
            body=info.body,
            files=self._files(root, info.sha),
            parents=info.parents,
            branch=info.branch,
        )

    def _parse_log(
        self,
        output: str,
        root: str | Path,
        branch: str = "",
    ) -> list[CommitInfo]:
        """Parse the field/record-separated log format into CommitInfo rows."""
        resolved_root = str(Path(root).resolve())
        commits: list[CommitInfo] = []
        for record in output.split("\x1e"):
            record = record.strip("\n")
            if not record:
                continue
            parts = record.split("\x1f")
            if len(parts) < 6:
                continue
            try:
                timestamp = int(parts[4])
            except ValueError:
                timestamp = 0
            parents = tuple(sha for sha in parts[5].split() if sha)
            commits.append(
                CommitInfo(
                    sha=parts[0].strip(),
                    subject=parts[1].strip(),
                    author=parts[3].strip(),
                    timestamp=timestamp,
                    repo_root=resolved_root,
                    body=parts[2].strip(),
                    parents=parents,
                    branch=branch,
                )
            )
        return commits

    def _files(self, root: str | Path, sha: str) -> tuple[str, ...]:
        """Files changed by one commit, including a root commit."""
        out = _run_git(
            root,
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            "--root",
            sha,
        )
        if out is None or out.returncode != 0:
            return ()
        return tuple(line.strip() for line in out.stdout.splitlines() if line.strip())


_BACKENDS: list[VCSBackend] = [GitBackend()]


def origin_url(backend: VCSBackend, root: str | Path) -> str:
    """Best origin fetch URL for a checkout, else its first remote."""
    remotes = backend.remotes(root)
    origin = next((item for item in remotes if item.name == "origin"), None)
    chosen = origin or (remotes[0] if remotes else None)
    if chosen is None:
        return ""
    return chosen.fetch_url or chosen.push_url


def web_remote(remote: str) -> str:
    """Best-effort https base URL for a git remote (no trailing .git)."""
    text = remote.strip()
    if not text:
        return ""
    if text.startswith("git@") and ":" in text:
        host, path = text[4:].split(":", 1)
        text = f"https://{host}/{path}"
    elif text.startswith("ssh://"):
        parsed = urllib.parse.urlparse(text)
        host = parsed.hostname or ""
        path = parsed.path.lstrip("/")
        if not host or not path:
            return ""
        text = f"https://{host}/{path}"
    elif not text.startswith(("http://", "https://")):
        return ""
    if text.endswith(".git"):
        text = text[:-4]
    return text.rstrip("/")


def commit_url(remote: str, sha: str) -> str:
    """Web URL for one commit, or empty when the remote cannot be mapped."""
    base = web_remote(remote)
    commit = sha.strip()
    if not base or not commit:
        return ""
    return f"{base}/commit/{commit}"


def file_url(remote: str, sha: str, path: str) -> str:
    """Web URL for one file at a commit, or empty when it cannot be mapped."""
    base = web_remote(remote)
    commit = sha.strip()
    file_path = path.strip().lstrip("/")
    if not base or not commit or not file_path:
        return ""
    quoted = "/".join(urllib.parse.quote(part, safe="") for part in file_path.split("/"))
    return f"{base}/blob/{commit}/{quoted}"


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
