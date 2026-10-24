"""Read-only source trail: where a plan row landed in each checkout.

The model is built from cached commit and forge links plus a small live git
status read per linked repo. It never calls the network and never writes to git.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .forge import RepoRef, detect_forge, parse_pull_url
from .vcs import commit_url, detect_backend, file_url, origin_url

if TYPE_CHECKING:
    from .store import Store


@dataclass(frozen=True)
class SourceFile:
    """One changed path at a commit, with a best-effort web URL."""

    path: str
    url: str = ""


@dataclass(frozen=True)
class SourceCommit:
    """One linked commit and its changed files."""

    sha: str
    subject: str = ""
    author: str = ""
    timestamp: int = 0
    stale: bool = False
    files: tuple[SourceFile, ...] = ()
    url: str = ""
    owners: tuple[str, ...] = ()

    @property
    def short(self) -> str:
        """Twelve-character SHA for compact rows."""
        return self.sha[:12]


@dataclass(frozen=True)
class SourcePull:
    """One linked pull request and its cached state."""

    number: int
    title: str = ""
    state: str = ""
    checks: str = ""
    reviews: str = ""
    url: str = ""
    merged_at: str = ""
    merge_commit_sha: str = ""
    stale: bool = False
    owners: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceRepo:
    """One checkout's commits, files, and pull requests."""

    path: str
    name: str
    remote: str = ""
    slug: str = ""
    branch: str = ""
    dirty: bool = False
    ahead: int = 0
    behind: int = 0
    detached: bool = False
    commits: tuple[SourceCommit, ...] = ()
    pulls: tuple[SourcePull, ...] = ()
    error: str = ""

    @property
    def file_count(self) -> int:
        """Unique changed paths across this repo's commits."""
        return len({item.path for commit in self.commits for item in commit.files})


@dataclass(frozen=True)
class SourceTrail:
    """Grouped provenance for one plan, milestone, or task."""

    kind: str
    oid: int
    title: str
    repos: tuple[SourceRepo, ...] = ()
    commit_count: int = 0
    file_count: int = 0
    pull_count: int = 0
    stale_count: int = 0

    @property
    def empty(self) -> bool:
        """True when nothing is linked."""
        return not self.repos


def _repo_name(path: str, remote: str = "") -> str:
    """Project name from a remote, else the checkout basename."""
    text = remote.strip().rstrip("/")
    if text:
        tail = text.rsplit(":", 1)[-1].rsplit("/", 1)[-1]
        if tail.lower().endswith(".git"):
            tail = tail[: -len(".git")]
        if tail:
            return tail
    name = Path(path).name if path else ""
    return name or "unknown"


def _owner_label(store: Store, parent_kind: str, parent_id: int) -> str:
    """Short, human owner label for one link parent."""
    if parent_kind == "task":
        task = store.get_task(parent_id)
        return f"T{parent_id} {task.title}" if task is not None else f"T{parent_id}"
    if parent_kind == "milestone":
        milestone = store.get_milestone(parent_id)
        return f"M{parent_id} {milestone.title}" if milestone is not None else f"M{parent_id}"
    plan = store.get_plan(parent_id)
    return f"P{parent_id} {plan.name}" if plan is not None else f"P{parent_id}"


def _repo_ref(remote: str) -> RepoRef | None:
    """Forge identity for a remote, or None."""
    if not remote:
        return None
    found = detect_forge(remote)
    return found[1] if found is not None else None


def _add_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def _scope_parents(store: Store, kind: str, obj_id: int) -> list[tuple[str, int]]:
    """Direct row plus descendant rows, without link deduplication."""
    out: list[tuple[str, int]] = [(kind, obj_id)]
    if kind == "milestone":
        out.extend(("task", task.id) for task in store.list_tasks(obj_id))
    elif kind == "plan":
        for milestone in store.list_milestones(obj_id):
            out.append(("milestone", milestone.id))
            out.extend(("task", task.id) for task in store.list_tasks(milestone.id))
    return out


def _commit_groups(
    store: Store, kind: str, obj_id: int
) -> dict[str, list[tuple[object, list[str]]]]:
    """Cached links grouped by repo root with owner labels."""
    groups: dict[str, list[tuple[object, list[str]]]] = {}
    for parent_kind, parent_id in _scope_parents(store, kind, obj_id):
        for link in store.list_links(parent_kind, parent_id):
            repo = str(getattr(link, "repo_root", "") or "")
            owners: list[str] = []
            _add_unique(owners, _owner_label(store, link.parent_kind, link.parent_id))
            groups.setdefault(repo, []).append((link, owners))
    return groups


def _commit_rows(
    store: Store,
    kind: str,
    obj_id: int,
    remote_by_path: dict[str, str],
) -> dict[str, list[SourceCommit]]:
    """Merge links by SHA within each repo, preserving first-seen order."""
    out: dict[str, list[SourceCommit]] = {}
    for repo, entries in _commit_groups(store, kind, obj_id).items():
        remote = remote_by_path.get(repo, "")
        by_sha: dict[str, SourceCommit] = {}
        for link, owners in entries:
            sha = str(getattr(link, "sha", "") or "")
            if not sha:
                continue
            previous = by_sha.get(sha)
            merged_owners = list(previous.owners if previous is not None else [])
            for owner in owners:
                _add_unique(merged_owners, owner)
            files = tuple(
                SourceFile(path=path, url=file_url(remote, sha, path))
                for path in tuple(getattr(link, "files", ()) or ())
            )
            by_sha[sha] = SourceCommit(
                sha=sha,
                subject=str(getattr(link, "subject", "") or ""),
                author=str(getattr(link, "author", "") or ""),
                timestamp=int(getattr(link, "timestamp", 0) or 0),
                stale=bool(getattr(link, "stale", False)),
                files=files,
                url=commit_url(remote, sha),
                owners=tuple(merged_owners),
            )
        out[repo] = list(by_sha.values())
    return out


def _pull_rows(store: Store, kind: str, obj_id: int) -> list[tuple[SourcePull, str]]:
    """Merged forge links with owners and the repo slug parsed from their URL."""
    by_number: dict[tuple[str, int], tuple[SourcePull, str]] = {}
    for parent_kind, parent_id in _scope_parents(store, kind, obj_id):
        for link in store.list_forge_links(parent_kind, parent_id, kind="pull"):
            number = int(getattr(link, "number", 0) or 0)
            if number <= 0:
                continue
            parsed = parse_pull_url(str(getattr(link, "url", "") or ""))
            slug = parsed[0].slug if parsed is not None else ""
            owner = _owner_label(store, link.parent_kind, link.parent_id)
            key = (slug, number)
            previous = by_number.get(key)
            owners = list(previous[0].owners if previous is not None else [])
            _add_unique(owners, owner)
            by_number[key] = (
                SourcePull(
                    number=number,
                    title=str(getattr(link, "title", "") or ""),
                    state=str(getattr(link, "state", "") or ""),
                    checks=str(getattr(link, "checks", "") or ""),
                    reviews=str(getattr(link, "reviews", "") or ""),
                    url=str(getattr(link, "url", "") or ""),
                    merged_at=str(getattr(link, "merged_at", "") or ""),
                    merge_commit_sha=str(getattr(link, "merge_commit_sha", "") or ""),
                    stale=bool(getattr(link, "stale", False)),
                    owners=tuple(owners),
                ),
                slug,
            )
    return list(by_number.values())


def _repo_meta(store: Store, kind: str, obj_id: int) -> dict[str, dict[str, object]]:
    """Explicit or inherited repo metadata keyed by normalized path."""
    out: dict[str, dict[str, object]] = {}
    for repo in store.effective_repos(kind, obj_id):
        path = str(repo.get("repo_path", "") or "")
        if path:
            out[path] = repo
    return out


def _repo_status(path: str, remote: str) -> tuple[dict[str, object], str]:
    """Live read-only status for one checkout."""
    state: dict[str, object] = {
        "branch": "",
        "dirty": False,
        "ahead": 0,
        "behind": 0,
        "detached": False,
        "remote": remote,
        "error": "",
    }
    if not path:
        state["error"] = "no checkout linked"
        return state, remote
    backend, root = detect_backend(path)
    if backend is None or root is None:
        state["error"] = "not a git checkout"
        return state, remote
    status = backend.status(root)
    resolved_remote = remote or origin_url(backend, root)
    state.update(
        {
            "branch": status.branch,
            "dirty": status.dirty,
            "ahead": status.ahead,
            "behind": status.behind,
            "detached": status.detached,
            "remote": resolved_remote,
        }
    )
    return state, resolved_remote


def _row_title(store: Store, kind: str, obj_id: int) -> str:
    parent = store.get_parent(kind, obj_id)
    if parent is None:
        return ""
    return str(getattr(parent, "name", getattr(parent, "title", "")) or "")


def _repo_paths(meta: dict[str, dict[str, object]], groups: dict[str, list]) -> list[str]:
    paths = list(meta)
    for path in groups:
        if path and path not in paths:
            paths.append(path)
    return paths


def _build_repo(
    path: str,
    info: dict[str, object],
    state: dict[str, object],
    remote: str,
    commits: list[SourceCommit],
    pulls: list[tuple[SourcePull, str]],
    matched: set[int],
) -> SourceRepo:
    ref = _repo_ref(remote)
    repo_pulls: list[SourcePull] = []
    for pull, slug in pulls:
        if ref is not None and slug and slug == ref.slug:
            repo_pulls.append(pull)
            matched.add(id(pull))
    return SourceRepo(
        path=path,
        name=_repo_name(path, remote),
        remote=remote,
        slug=ref.slug if ref is not None else "",
        branch=str(state["branch"] or info.get("branch", "") or ""),
        dirty=bool(state["dirty"]),
        ahead=int(str(state["ahead"] or 0)),
        behind=int(str(state["behind"] or 0)),
        detached=bool(state["detached"]),
        commits=tuple(commits),
        pulls=tuple(repo_pulls),
        error=str(state["error"] or ""),
    )


def _attach_unmatched_pulls(
    repos: list[SourceRepo],
    pulls: list[tuple[SourcePull, str]],
    matched: set[int],
) -> None:
    if not repos or len(matched) >= len(pulls):
        return
    first = repos[0]
    extra = tuple(pull for pull, _slug in pulls if id(pull) not in matched)
    repos[0] = SourceRepo(
        path=first.path,
        name=first.name,
        remote=first.remote,
        slug=first.slug,
        branch=first.branch,
        dirty=first.dirty,
        ahead=first.ahead,
        behind=first.behind,
        detached=first.detached,
        commits=first.commits,
        pulls=first.pulls + extra,
        error=first.error,
    )


def _trail_counts(repos: list[SourceRepo]) -> tuple[int, int, int, int]:
    commits = [commit for repo in repos for commit in repo.commits]
    files = {item.path for commit in commits for item in commit.files}
    stale = sum(1 for commit in commits if commit.stale)
    stale += sum(1 for repo in repos for pull in repo.pulls if pull.stale)
    commit_count = len({(repo.path, commit.sha) for repo in repos for commit in repo.commits})
    pull_count = len({(repo.slug, pull.number) for repo in repos for pull in repo.pulls})
    return commit_count, len(files), pull_count, stale


def build_source_trail(store: Store, kind: str, obj_id: int) -> SourceTrail:
    """Build the grouped source trail for one row without network access."""
    meta = _repo_meta(store, kind, obj_id)
    groups = _commit_groups(store, kind, obj_id)
    paths = _repo_paths(meta, groups)
    pulls = _pull_rows(store, kind, obj_id)
    states: dict[str, tuple[dict[str, object], str]] = {}
    for path in paths:
        info = meta.get(path, {})
        remote = str(info.get("repo_remote", "") or "")
        states[path] = _repo_status(path, remote)
    remote_by_path = {path: state[1] for path, state in states.items()}
    commit_map = _commit_rows(store, kind, obj_id, remote_by_path)
    repos: list[SourceRepo] = []
    matched_pulls: set[int] = set()
    for path in paths:
        state, remote = states[path]
        repos.append(
            _build_repo(
                path,
                meta.get(path, {}),
                state,
                remote,
                commit_map.get(path, []),
                pulls,
                matched_pulls,
            )
        )
    _attach_unmatched_pulls(repos, pulls, matched_pulls)
    commit_count, file_count, pull_count, stale_count = _trail_counts(repos)
    return SourceTrail(
        kind=kind,
        oid=obj_id,
        title=_row_title(store, kind, obj_id),
        repos=tuple(repos),
        commit_count=commit_count,
        file_count=file_count,
        pull_count=pull_count,
        stale_count=stale_count,
    )
