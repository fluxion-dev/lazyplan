"""Startup health: what lazyplan's agent features need, and what each gap costs.

A finding groups the missing catalog items it can install (``items``), or
names a manual ``fix`` when lazyplan cannot repair it. ``decision`` is the
remembered "not now" or "never" that keeps it from prompting. This module
never writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lazyplan.infrastructure.integrations import HOOK, HOST_LABELS, IntegrationItem

from .integrations import inspect
from .layout import SetupChoice
from .state import SetupState

ERROR = "error"

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
    def items(self) -> tuple[IntegrationItem, ...]:
        """Installable items behind every finding."""
        return tuple(item for finding in self.findings for item in finding.items)

    def hosts(self, items: tuple[IntegrationItem, ...]) -> list[str]:
        """Agent labels whose hooks or skills these items change."""
        hosts = {item.host for item in items if item.kind == HOOK and item.host}
        return [HOST_LABELS.get(host, host) for host in sorted(hosts)]


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


def check(
    choice: SetupChoice,
    state: SetupState,
    root: Path | None,
    home: Path | None = None,
    version: str = "",
) -> HealthReport:
    """Return every gap for the remembered setup, without writing."""
    if choice.explicit_db:
        return HealthReport()
    inspection = inspect(choice, state, root, home, version)
    findings = _integration_findings(inspection.pending, state, decided=False)
    findings += _integration_findings(inspection.suppressed, state, decided=True)
    return HealthReport(findings=tuple(findings))
