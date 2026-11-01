"""Pure builder for the GIT pane's at-a-glance checkout and provenance view."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ...design import (
    SECTION_ICON,
    STATE_ICON,
    escape_markup,
    truncate,
)

MAX_REPOS = 3
MAX_COMMITS = 4
MAX_PULLS = 3


@dataclass(frozen=True)
class GitDocument:
    """The rendered GIT body and its one-line border subtitle."""

    body: str
    summary: str = ""

    def render(self) -> str:
        """Return the Rich markup body."""
        return self.body


def _state_word(state: Mapping[str, Any]) -> tuple[str, str]:
    if state.get("detached"):
        return STATE_ICON["detached"], "detached"
    if state.get("branch"):
        return (STATE_ICON["dirty"] if state.get("dirty") else STATE_ICON["clean"]), (
            "dirty" if state.get("dirty") else "clean"
        )
    return "·", "unknown"


def _tracking(state: Mapping[str, Any]) -> str:
    ahead = int(state.get("ahead", 0) or 0)
    behind = int(state.get("behind", 0) or 0)
    bits = []
    if ahead:
        bits.append(f"↑{ahead}")
    if behind:
        bits.append(f"↓{behind}")
    return " ".join(bits)


def _repo_line(state: Mapping[str, Any]) -> str:
    name = escape_markup(str(state.get("name") or state.get("path") or "checkout"))
    branch = escape_markup(
        str(state.get("branch") or ("detached" if state.get("detached") else "unknown"))
    )
    icon, word = _state_word(state)
    color = "green" if word == "clean" else ("red" if word == "dirty" else "dim")
    line = f"[bold]{SECTION_ICON['git']} {name}[/] [dim]{branch}[/] [{color}]{icon} {word}[/]"
    tracking = _tracking(state)
    if tracking:
        line += f" [dim]{tracking}[/]"
    return line


def _commit_line(link: Mapping[str, Any]) -> str:
    short = escape_markup(str(link.get("sha", ""))[:12])
    subject = escape_markup(str(link.get("subject", "") or "(no subject)"))
    files = link.get("files") or ()
    count = f" [dim]· {len(files)} files[/]" if files else ""
    stale = " [red]· stale[/]" if link.get("stale") else ""
    return (
        f"[dim]{SECTION_ICON['commits']} {short}[/] [dim]·[/] {truncate(subject, 44)}{count}{stale}"
    )


def _pull_line(link: Mapping[str, Any]) -> str:
    state = str(link.get("state", "") or "open")
    color = {"merged": "green", "open": "yellow", "draft": "dim", "closed": "red"}.get(state, "dim")
    number = link.get("number", "?")
    title = escape_markup(str(link.get("title", "") or ""))
    checks = str(link.get("checks", "") or "")
    suffix = ""
    if checks and checks != "none":
        check_color = {"pass": "green", "fail": "red", "pending": "yellow"}.get(checks, "dim")
        suffix = f" [{check_color}]· checks {escape_markup(checks)}[/]"
    return (
        f"[magenta]{SECTION_ICON['pulls']} PR #{number}[/] "
        f"[{color}]{escape_markup(state)}[/] {truncate(title, 44)}{suffix}"
    )


def build_git(
    full: Mapping[str, Any],
    repo_states: Sequence[Mapping[str, Any]] = (),
) -> GitDocument:
    """Build the GIT pane for one selected row.

    The pane answers three questions at a glance: which checkouts are
    involved and in what state, which commits landed, and which pull
    requests carry them. It is deliberately bounded so the preview above
    keeps the room.
    """
    repos = list(repo_states)[:MAX_REPOS]
    links = full.get("effective_links") or full.get("links") or []
    pulls = full.get("effective_forge_links") or full.get("forge_links") or []
    repo_count = len(full.get("effective_repos") or full.get("repos") or [])
    lines: list[str] = []
    for state in repos:
        lines.append(_repo_line(state))
    for link in links[:MAX_COMMITS]:
        lines.append(_commit_line(link))
    for pull in pulls[:MAX_PULLS]:
        lines.append(_pull_line(pull))
    hidden_commits = max(0, len(links) - MAX_COMMITS)
    hidden_pulls = max(0, len(pulls) - MAX_PULLS)
    if hidden_commits or hidden_pulls:
        hidden = []
        if hidden_commits:
            hidden.append(f"{hidden_commits} more commits")
        if hidden_pulls:
            hidden.append(f"{hidden_pulls} more PRs")
        lines.append(f"[dim]+{' · '.join(hidden)}[/]")
    if not lines:
        lines = [
            "[dim]no linked checkouts[/]",
            "[dim]g opens the source trail[/]",
        ]
    counts = []
    if links:
        counts.append(f"{len(links)} commits")
    if pulls:
        counts.append(f"{len(pulls)} PRs")
    if repo_count:
        counts.append(f"{repo_count} repos")
    summary = f" {' · '.join(counts)} " if counts else ""
    return GitDocument(body="\n".join(lines), summary=summary)
