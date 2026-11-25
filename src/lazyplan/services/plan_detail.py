"""Resume contract for plan milestones and tasks.

Promotion is the last moment a reviewed definition becomes rows an agent may
resume cold. This module names the context a milestone and task must carry so a
fresh or recovering agent does not have to infer the approach, touch-points,
prerequisites, commit slices, verification, or guardrails.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MILESTONE_SECTIONS: tuple[str, ...] = ("Outcome", "Scope", "Inputs", "Slices")
TASK_SECTIONS: tuple[str, ...] = (
    "Approach",
    "Touch",
    "Inputs",
    "Commit",
    "Verify",
    "Guardrails",
)

_LABEL = re.compile(r"^\s{0,3}(?:\*\*)?([A-Za-z][A-Za-z /-]{0,30}?)(?:\*\*)?\s*:\s*(.*)$")
_HEADING = re.compile(r"^\s{0,3}#{2,6}\s+([A-Za-z][A-Za-z /-]{0,30}?)\s*$")
_PATH = re.compile(
    r"(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.*/-]*"
    r"|\b[A-Za-z0-9_.-]+\.(?:py|pyi|md|json|jsonc|toml|yaml|yml|ini|cfg|txt"
    r"|sh|bash|zsh|ts|tsx|js|jsx|css|scss|html|xml|sql|rs|go|java|kt|rb|php"
    r"|c|h|cpp|hpp|cs|swift|lock)\b"
)

_ALIASES: dict[str, str] = {
    "outcome": "outcome",
    "value": "outcome",
    "user value": "outcome",
    "scope": "scope",
    "in scope": "scope",
    "out of scope": "scope",
    "inputs": "inputs",
    "input": "inputs",
    "prerequisites": "inputs",
    "prereqs": "inputs",
    "requires": "inputs",
    "depends on": "inputs",
    "slices": "slices",
    "slice": "slices",
    "commit slices": "slices",
    "sequence": "slices",
    "order": "slices",
    "steps": "slices",
    "approach": "approach",
    "how": "approach",
    "implementation": "approach",
    "touch": "touch",
    "touches": "touch",
    "touchpoints": "touch",
    "touch points": "touch",
    "files": "touch",
    "paths": "touch",
    "commit": "commit",
    "commits": "commit",
    "commit slice": "commit",
    "verify": "verify",
    "verification": "verify",
    "test": "verify",
    "tests": "verify",
    "check": "verify",
    "checks": "verify",
    "guardrails": "guardrails",
    "guardrail": "guardrails",
    "guards": "guardrails",
    "invariants": "guardrails",
    "constraints": "guardrails",
    "non-goals": "guardrails",
    "non goals": "guardrails",
    "do not": "guardrails",
}

_DISPLAY: dict[str, str] = {
    section.lower(): section for section in MILESTONE_SECTIONS + TASK_SECTIONS
}


class PlanDetailError(ValueError):
    """A milestone or task leaves the resume contract implicit."""


@dataclass(frozen=True)
class DetailIssue:
    """One missing or unusable resume-contract section."""

    section: str
    message: str


def _canonical(label: str) -> str | None:
    """Map one written label to its canonical section name."""
    key = " ".join(label.lower().replace("_", " ").split()).rstrip(":")
    return _ALIASES.get(key)


def sections(text: str) -> dict[str, str]:
    """Read labeled sections, folding continuation lines into their label.

    ``Label:`` paragraphs, ``**Label:**`` lines, and ``## Label`` headings are
    accepted. Unrecognized labels stay with the section they appear in, and an
    unrecognized heading ends the current section.
    """
    found: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        heading = _HEADING.match(line)
        if heading:
            current = _canonical(heading.group(1))
            if current is not None:
                found.setdefault(current, [])
            continue
        label = _LABEL.match(line)
        if label:
            canonical = _canonical(label.group(1))
            if canonical is not None:
                current = canonical
                found.setdefault(canonical, [])
                if label.group(2).strip():
                    found[canonical].append(label.group(2).strip())
                continue
        if current is not None:
            found.setdefault(current, []).append(line)
    return {key: "\n".join(parts).strip() for key, parts in found.items()}


def _issues(text: str, required: tuple[str, ...]) -> list[DetailIssue]:
    """List the required sections that are absent or unusable."""
    found = sections(text)
    issues = [
        DetailIssue(_DISPLAY[name.lower()], "is missing")
        for name in required
        if not found.get(name.lower())
    ]
    if found.get("touch") and not _PATH.search(found["touch"]):
        issues.append(DetailIssue("Touch", "must name at least one concrete path"))
    return issues


def milestone_issues(description: str) -> list[DetailIssue]:
    """Resume-contract gaps in one milestone description."""
    return _issues(description, MILESTONE_SECTIONS)


def task_issues(description: str) -> list[DetailIssue]:
    """Resume-contract gaps in one task description."""
    return _issues(description, TASK_SECTIONS)


def describe(issues: list[DetailIssue]) -> str:
    """Render issues as one sentence for an error or lint finding."""
    missing = [issue.section for issue in issues if issue.message == "is missing"]
    parts: list[str] = []
    if len(missing) == 1:
        parts.append(f"{missing[0]} is missing")
    elif missing:
        parts.append(f"{', '.join(missing[:-1])} and {missing[-1]} are missing")
    parts.extend(
        f"{issue.section} {issue.message}" for issue in issues if issue.message != "is missing"
    )
    return "; ".join(parts) if parts else "resume contract is complete"


def require_milestone(path: str, description: str) -> None:
    """Refuse a milestone that leaves its resume contract implicit."""
    issues = milestone_issues(description)
    if issues:
        raise PlanDetailError(f"{path}: resume contract incomplete: {describe(issues)}")


def require_task(path: str, description: str) -> None:
    """Refuse a task that leaves its resume contract implicit."""
    issues = task_issues(description)
    if issues:
        raise PlanDetailError(f"{path}: resume contract incomplete: {describe(issues)}")
