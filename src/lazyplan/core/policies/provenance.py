"""Pure provenance rules: trailers, branches, and forge state."""

from __future__ import annotations

import re

_LAZYPLAN_TRAILER = re.compile(r"(?i)^lazyplan:\s*(.+)$")
_LAZYPLAN_REF = re.compile(r"(?i)^([ptm])\s*#?(\d+)$")
_LAZYPLAN_BRANCH = re.compile(r"^(task|plan|milestone)/(\d+)(?:-|$)")
_KIND_BY_LETTER = {"p": "plan", "m": "milestone", "t": "task"}
_LETTER_BY_KIND = {"plan": "P", "milestone": "M", "task": "T"}


def trailer_refs(message: str) -> list[tuple[str, int]]:
    """Explicit Lazyplan trailer refs in one commit message."""
    found: set[tuple[str, int]] = set()
    for line in message.splitlines():
        match = _LAZYPLAN_TRAILER.match(line.strip())
        if not match:
            continue
        for token in re.split(r"[,\s]+", match.group(1)):
            ref = _LAZYPLAN_REF.match(token.strip())
            if ref:
                found.add((_KIND_BY_LETTER[ref.group(1).lower()], int(ref.group(2))))
    return sorted(found, key=lambda item: (item[0], item[1]))


def branch_ref(branch: str) -> tuple[str, int] | None:
    """Plan/milestone/task ref encoded in a branch name."""
    match = _LAZYPLAN_BRANCH.match(branch)
    if not match:
        return None
    return match.group(1), int(match.group(2))


def letter_for_kind(kind: str) -> str:
    """Row label letter for one kind."""
    return _LETTER_BY_KIND[kind]


def pr_state(pr: dict) -> str:
    """Normalize a pull request to open/draft/merged/closed."""
    if pr.get("merged_at"):
        return "merged"
    state = str(pr.get("state", "") or "")
    if state == "open" and pr.get("draft"):
        return "draft"
    return state


def checks_state(data: object) -> str:
    """Aggregate check runs to pass/fail/pending/none."""
    if not isinstance(data, dict):
        return "none"
    runs = data.get("check_runs", [])
    if not isinstance(runs, list) or not runs:
        return "none"
    statuses = [str(run.get("status", "") or "") for run in runs if isinstance(run, dict)]
    conclusions = [str(run.get("conclusion", "") or "") for run in runs if isinstance(run, dict)]
    if any(status != "completed" for status in statuses):
        return "pending"
    if any(
        conclusion in {"failure", "cancelled", "timed_out", "action_required"}
        for conclusion in conclusions
    ):
        return "fail"
    if all(conclusion in {"success", "neutral", "skipped"} for conclusion in conclusions):
        return "pass"
    return "none"
