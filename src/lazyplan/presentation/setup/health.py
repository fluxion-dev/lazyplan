"""Startup health: what lazyplan's agent features need, and what each gap costs.

A finding groups the missing catalog items it can install (``items``), or
names a manual ``fix`` when lazyplan cannot repair it. ``decision`` is the
remembered "not now" or "never" that keeps it from prompting. ``check``
never writes; ``HealthContext.install`` does.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from lazyplan.infrastructure.integrations import HOOK, HOST_LABELS, IntegrationItem
from lazyplan.infrastructure.repo import find_repo_root

from .apply import choice_from_state
from .integrations import ReviewResult, inspect, install_items, suppressing_decision
from .layout import SetupChoice
from .state import SetupState, load_state, save_state, timestamp

ERROR = "error"
WARNING = "warning"
TOKEN_ENV = ("LAZYPLAN_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN")

Which = Callable[[str], str | None]
Run = Callable[[list[str]], int]

SKILL_COST = "Agents won't load lazyplan's instructions for planning and tracking work."
HOOK_COST = (
    "{host} sessions aren't tracked: no agent registry, no active plan in prompts,"
    " and no commit or stop checks."
)


@dataclass(frozen=True)
class HealthFinding:
    """One gap and the capability it costs."""

    id: str
    label: str
    capability: str
    severity: str = ERROR
    fix: str = ""
    decision: str = ""
    host: str = ""
    items: tuple[IntegrationItem, ...] = ()

    @property
    def fixable(self) -> bool:
        """True when lazyplan can install this itself."""
        return bool(self.items)

    @property
    def open(self) -> bool:
        """True unless a remembered decision hides it."""
        return not self.decision

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe summary."""
        return {
            "id": self.id,
            "label": self.label,
            "capability": self.capability,
            "severity": self.severity,
            "fix": self.fix,
            "decision": self.decision,
            "host": self.host,
            "fixable": self.fixable,
            "items": [item.id for item in self.items],
        }


@dataclass(frozen=True)
class HealthReport:
    """Every finding for one setup context."""

    findings: tuple[HealthFinding, ...] = ()

    @property
    def open(self) -> tuple[HealthFinding, ...]:
        """Findings no remembered decision hides."""
        return tuple(finding for finding in self.findings if finding.open)

    @property
    def should_prompt(self) -> bool:
        """True when an open error needs the user's attention."""
        return any(finding.severity == ERROR for finding in self.open)

    def hosts(self, items: tuple[IntegrationItem, ...]) -> list[str]:
        """Agent labels whose hooks or skills these items change."""
        hosts = {item.host for item in items if item.kind == HOOK and item.host}
        return [HOST_LABELS.get(host, host) for host in sorted(hosts)]


def items_of(findings: tuple[HealthFinding, ...]) -> tuple[IntegrationItem, ...]:
    """Installable items behind these findings, in order."""
    return tuple(item for finding in findings for item in finding.items)


def _decision(state: SetupState, items: tuple[IntegrationItem, ...]) -> str:
    choice = state.integration_choices.get(items[0].id) or {}
    return str(choice.get("decision", "") or "")


def _integration_findings(
    items: tuple[IntegrationItem, ...],
    state: SetupState,
    decided: bool,
) -> list[HealthFinding]:
    """One finding per skill and one per hook host."""
    groups: dict[str, list[IntegrationItem]] = {}
    for item in items:
        key = f"hook:{item.host}" if item.kind == HOOK else item.id
        groups.setdefault(key, []).append(item)
    findings = []
    for key, members in groups.items():
        grouped = tuple(members)
        first = grouped[0]
        if first.kind == HOOK:
            host = HOST_LABELS.get(first.host, first.host)
            label, cost = f"{host} hooks", HOOK_COST.format(host=host)
        else:
            label, cost = first.label, SKILL_COST
        findings.append(
            HealthFinding(
                id=key,
                label=label,
                capability=cost,
                decision=_decision(state, grouped) if decided else "",
                host=first.host,
                items=grouped,
            )
        )
    return findings


LPUI = HealthFinding(
    id="tool:lpui",
    label="lpui on PATH",
    capability=(
        "Hooks and agents run `lpui`, so hooks fail silently and agents can't read"
        " or update the plan."
    ),
    fix=(
        "Add the folder holding lpui to PATH (`uv tool update-shell` or"
        " `pipx ensurepath`), then open a new terminal."
    ),
)
GIT = HealthFinding(
    id="tool:git",
    label="git on PATH",
    capability="Commit links, `task start`, `task finish`, and `git scan` don't work.",
    fix="Install Git from https://git-scm.com/downloads.",
)
GH = HealthFinding(
    id="tool:gh",
    label="GitHub CLI",
    capability="Pull request and check status can't refresh without a GitHub token.",
    severity=WARNING,
    fix="Install GitHub CLI from https://cli.github.com and run `gh auth login`.",
)
GH_AUTH = HealthFinding(
    id="tool:gh-auth",
    label="GitHub CLI login",
    capability="gh isn't logged in, so pull request and check status can't refresh.",
    severity=WARNING,
    fix="Run `gh auth login`.",
)


def _exit_code(argv: list[str]) -> int:
    try:
        return subprocess.run(argv, capture_output=True, timeout=5, check=False).returncode
    except (OSError, subprocess.SubprocessError):
        return 1


def _missing_tools(which: Which, run: Run, env: Mapping[str, str]) -> list[HealthFinding]:
    """Tools lazyplan shells out to; gh is skipped when a token is set."""
    missing = [tool for tool, binary in ((LPUI, "lpui"), (GIT, "git")) if which(binary) is None]
    if any(env.get(name) for name in TOKEN_ENV):
        return missing
    gh = which("gh")
    if gh is None:
        missing.append(GH)
    elif run([gh, "auth", "token"]) != 0:
        missing.append(GH_AUTH)
    return missing


def check(
    choice: SetupChoice,
    state: SetupState,
    root: Path | None,
    home: Path | None = None,
    version: str = "",
    which: Which = shutil.which,
    run: Run = _exit_code,
    env: Mapping[str, str] | None = None,
) -> HealthReport:
    """Return every gap for the remembered setup, without writing."""
    if choice.explicit_db:
        return HealthReport()
    inspection = inspect(choice, state, root, home, version)
    findings = _integration_findings(inspection.pending, state, decided=False)
    findings += _integration_findings(inspection.suppressed, state, decided=True)
    for tool in _missing_tools(which, run, os.environ if env is None else env):
        remembered = state.integration_choices.get(tool.id)
        decision = suppressing_decision(remembered, "", version)
        findings.append(replace(tool, decision=decision))
    return HealthReport(findings=tuple(findings))


@dataclass(frozen=True)
class HealthContext:
    """The remembered setup one startup check runs against."""

    choice: SetupChoice
    state: SetupState
    root: Path | None
    home: Path
    version: str

    def report(self) -> HealthReport:
        """Run the check for this context."""
        return check(self.choice, self.state, self.root, self.home, self.version)

    def install(self, findings: tuple[HealthFinding, ...]) -> ReviewResult:
        """Install every fixable item behind these findings."""
        return install_items(
            items_of(findings), self.choice, self.state, self.root, self.home, self.version
        )

    def decide(self, findings: tuple[HealthFinding, ...], decision: str) -> None:
        """Remember "deferred" or "never" for these findings and save state."""
        seen_at = timestamp()
        for finding in findings:
            keys = [(item.id, item.fingerprint) for item in finding.items] or [(finding.id, "")]
            for key, fingerprint in keys:
                self.state.integration_choices[key] = {
                    "decision": decision,
                    "fingerprint": fingerprint,
                    "version": self.version,
                    "seen_at": seen_at,
                }
        save_state(self.state, self.home)


def current(cwd: Path, home: Path | None = None, version: str = "") -> HealthContext:
    """Context for the checkout at ``cwd`` and the remembered setup."""
    home = home or Path.home()
    state = load_state(home)
    return HealthContext(choice_from_state(state), state, find_repo_root(cwd), home, version)
