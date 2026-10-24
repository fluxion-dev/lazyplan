"""Forge integration: provider-neutral repo identity and GitHub remotes.

Stdlib only. No network calls live here; the GitHub client is added separately.
"""

from __future__ import annotations

import os
import re
import subprocess
import urllib.parse
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

GITHUB_HOST = "github.com"
TOKEN_ENVS = ("LAZYPLAN_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN")
_TOKEN_PATTERN = re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")


class ForgeError(Exception):
    """Base error for forge identity and API failures."""


class UnsupportedRemote(ForgeError):
    """The remote is not a supported forge URL."""


@dataclass(frozen=True)
class RepoRef:
    """Canonical owner/repo identity for one forge host."""

    provider: str
    host: str
    owner: str
    repo: str

    @property
    def slug(self) -> str:
        """owner/repo, the forge-facing short identity."""
        return f"{self.owner}/{self.repo}"

    @property
    def web_url(self) -> str:
        """Repository web URL."""
        return f"https://{self.host}/{self.owner}/{self.repo}"


@dataclass(frozen=True)
class AuthStatus:
    """Resolved GitHub credentials; the token never appears in repr."""

    source: str = "none"
    token: str = field(default="", repr=False)

    @property
    def available(self) -> bool:
        """True when a non-empty token was found."""
        return bool(self.token)


def _gh_token() -> str | None:
    """Ask the GitHub CLI for a token; None when gh is missing or unauthenticated."""
    try:
        out = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        return None
    if out.returncode != 0:
        return None
    token = out.stdout.strip()
    return token or None


def resolve_auth(
    env: Mapping[str, str] | None = None,
    gh_runner: Callable[[], str | None] | None = None,
) -> AuthStatus:
    """Resolve a GitHub token: explicit env vars first, then the gh CLI."""
    values = os.environ if env is None else env
    for name in TOKEN_ENVS:
        token = str(values.get(name, "") or "").strip()
        if token:
            return AuthStatus(source=name, token=token)
    gh_token = (gh_runner or _gh_token)()
    if gh_token:
        return AuthStatus(source="gh", token=gh_token.strip())
    return AuthStatus()


def redact(text: str, token: str = "") -> str:
    """Remove a known token and any GitHub-token-shaped string from text."""
    cleaned = text.replace(token, "[redacted]") if token else text
    return _TOKEN_PATTERN.sub("[redacted]", cleaned)


class Forge(ABC):
    """One forge provider (GitHub is the only implementation for now)."""

    name: str = ""
    host: str = ""

    @abstractmethod
    def parse_remote(self, remote: str) -> RepoRef | None:
        """Parse a remote URL into a repo identity, or None when not applicable."""
        raise NotImplementedError


def _split_remote(remote: str) -> tuple[str, str] | None:
    """Host and path from https, ssh, git, or scp-style remotes."""
    text = remote.strip()
    if not text:
        return None
    if "://" in text:
        parsed = urllib.parse.urlparse(text)
        if parsed.scheme not in ("http", "https", "ssh", "git", "git+ssh"):
            return None
        host = parsed.hostname or ""
        return (host, parsed.path) if host else None
    if ":" not in text or text.startswith("/"):
        return None
    host, _, path = text.partition(":")
    host = host.rsplit("@", 1)[-1]
    return (host, path) if host else None


def _repo_path(path: str) -> tuple[str, str] | None:
    """Owner and repo from a forge URL path."""
    cleaned = urllib.parse.unquote(path).strip().strip("/")
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]
    parts = [part for part in cleaned.split("/") if part]
    if len(parts) != 2:
        return None
    return parts[0], parts[1]


class GitHubForge(Forge):
    """GitHub remote identity for github.com."""

    name = "github"
    host = GITHUB_HOST

    def parse_remote(self, remote: str) -> RepoRef | None:
        """Parse a github.com remote; typed error for other forge hosts."""
        parts = _split_remote(remote)
        if parts is None:
            return None
        host, path = parts
        if host.lower() != self.host:
            raise UnsupportedRemote(f"unsupported forge host {host!r}")
        repo_path = _repo_path(path)
        if repo_path is None:
            raise UnsupportedRemote(f"not an owner/repo GitHub remote: {remote!r}")
        owner, repo = repo_path
        return RepoRef(provider=self.name, host=self.host, owner=owner, repo=repo)


_FORGES: list[Forge] = [GitHubForge()]


def forges() -> list[Forge]:
    """Registered forge providers; append new ones here."""
    return list(_FORGES)


def detect_forge(remote: str) -> tuple[Forge, RepoRef] | None:
    """First provider that claims this remote, else None."""
    for forge in _FORGES:
        try:
            ref = forge.parse_remote(remote)
        except UnsupportedRemote:
            continue
        if ref is not None:
            return forge, ref
    return None


def parse_pull_url(url: str) -> tuple[RepoRef, int] | None:
    """Parse a github.com pull request URL into its repo and number."""
    parsed = urllib.parse.urlparse(url.strip())
    if (parsed.hostname or "").lower() != GITHUB_HOST:
        return None
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) != 4 or parts[2] != "pull":
        return None
    try:
        number = int(parts[3])
    except ValueError:
        return None
    if number <= 0:
        return None
    return RepoRef("github", GITHUB_HOST, parts[0], parts[1]), number
