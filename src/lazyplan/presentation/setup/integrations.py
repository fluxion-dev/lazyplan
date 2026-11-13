"""Read-only inspection of installed and pending integrations.

Setup resolves the remembered layout, then compares the shipped catalog
with the files on disk and the choices remembered in ``setup.json``. This
module never writes: review and apply live in the setup flow.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from lazyplan.infrastructure import hook_install, skills, textfile
from lazyplan.infrastructure.integrations import (
    HOOK,
    SKILL,
    IntegrationItem,
    catalog,
    hook_id,
    hook_paths,
    skill_paths,
)

from . import layout, ui
from .layout import SetupChoice
from .state import SetupState, save_state, timestamp

__all__ = [
    "Inspection",
    "ReviewResult",
    "inspect",
    "remember_installed",
    "review_pending",
]


@dataclass(frozen=True)
class Inspection:
    """Installed and pending catalog items for one setup context."""

    installed: tuple[IntegrationItem, ...]
    pending: tuple[IntegrationItem, ...]
    suppressed: tuple[IntegrationItem, ...] = ()


@dataclass(frozen=True)
class ReviewResult:
    """Outcome of one integration review."""

    decision: str
    installed: tuple[str, ...] = ()
    backups: tuple[str, ...] = ()
    pending: tuple[IntegrationItem, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe summary."""
        return {
            "decision": self.decision,
            "installed": list(self.installed),
            "backups": list(self.backups),
            "pending": [item.to_dict() for item in self.pending],
        }


def _installed_ids(
    choice: SetupChoice,
    root: Path | None,
    home: Path,
    items: tuple[IntegrationItem, ...],
) -> set[str]:
    """Return catalog ids whose files are present, without writing."""
    installed: set[str] = set()
    plan = skills.plan_choice(choice, root, home)
    if plan.scope != "none":
        for item in items:
            if item.kind != SKILL:
                continue
            paths = skill_paths(
                item,
                plan.scope,
                root,
                home,
                plan.tools,
                plan.skills_dir,
            )
            if any(path.is_file() for path in paths):
                installed.add(item.id)
    for host in hook_install.HOSTS:
        for event in hook_install.installed_events(home, host):
            installed.add(hook_id(host, event))
    return installed


def _enabled(item: IntegrationItem, state: SetupState, choice: SetupChoice) -> bool:
    if item.kind == SKILL:
        return state.skills_enabled and not choice.no_skills
    selected = choice.agents if choice.agents is not None else state.agents
    return state.hooks_enabled and item.host in selected


def suppressing_decision(
    remembered: dict[str, Any] | None,
    fingerprint: str,
    version: str,
) -> str:
    """The remembered decision that still hides a missing item, or ``""``."""
    if remembered is None:
        return ""
    decision = str(remembered.get("decision", "") or "")
    stored = remembered.get("fingerprint")
    if stored and stored != fingerprint:
        return ""
    if decision == "never":
        return decision
    if decision == "deferred" and remembered.get("version", "") == version:
        return decision
    return ""


def _suppressed(item: IntegrationItem, state: SetupState, version: str) -> bool:
    remembered = state.integration_choices.get(item.id)
    return bool(suppressing_decision(remembered, item.fingerprint, version))


def inspect(
    choice: SetupChoice,
    state: SetupState,
    root: Path | None,
    home: Path | None = None,
    version: str = "",
) -> Inspection:
    """Return installed and pending catalog items for the remembered setup."""
    if choice.explicit_db:
        return Inspection(installed=(), pending=())
    home = home or Path.home()
    items = catalog(home)
    installed_ids = _installed_ids(choice, root, home, items)
    installed = tuple(item for item in items if item.id in installed_ids)
    missing = tuple(
        item for item in items if _enabled(item, state, choice) and item.id not in installed_ids
    )
    pending = tuple(item for item in missing if not _suppressed(item, state, version))
    suppressed = tuple(item for item in missing if _suppressed(item, state, version))
    return Inspection(installed=installed, pending=pending, suppressed=suppressed)


def remember_installed(
    inspection: Inspection,
    state: SetupState,
    version: str,
) -> bool:
    """Adopt installed items so a missing file is not mistaken for a new one."""
    changed = False
    seen_at = timestamp()
    for item in inspection.installed:
        if item.id in state.integration_choices:
            continue
        state.integration_choices[item.id] = {
            "decision": "installed",
            "fingerprint": item.fingerprint,
            "version": version,
            "seen_at": seen_at,
        }
        changed = True
    return changed


def _rows(
    items: tuple[IntegrationItem, ...],
    choice: SetupChoice,
    root: Path | None,
    home: Path,
) -> list[tuple[str, str]]:
    """Label and target text for each item in the review."""
    plan = skills.plan_choice(choice, root, home)
    rows: list[tuple[str, str]] = []
    for item in items:
        if item.kind == SKILL:
            paths = skill_paths(
                item,
                plan.scope,
                root,
                home,
                plan.tools,
                plan.skills_dir,
            )
        else:
            paths = hook_paths(item, home)
        target = ", ".join(str(path) for path in paths) or "no destination"
        rows.append((f"{item.kind}: {item.label}", target))
    return rows


def _install_skills(
    items: tuple[IntegrationItem, ...],
    choice: SetupChoice,
    root: Path | None,
    home: Path,
    backup_dir: Path,
) -> list[str]:
    """Write pending skill files that changed, backing each one up."""
    plan = skills.plan_choice(choice, root, home)
    changed: list[str] = []
    for item in items:
        if item.kind != SKILL:
            continue
        content = skills.render_skill(item.skill)
        for path in skill_paths(
            item,
            plan.scope,
            root,
            home,
            plan.tools,
            plan.skills_dir,
        ):
            if path.is_file():
                try:
                    current = textfile.read(path)
                except OSError:
                    current = ""
                if current == content:
                    continue
                layout.backup_file(backup_dir, path)
            path.parent.mkdir(parents=True, exist_ok=True)
            textfile.write(path, content)
            changed.append(str(path))
    return changed


def _install_hooks(
    items: tuple[IntegrationItem, ...],
    home: Path,
    mode: str,
) -> tuple[list[str], list[str], set[str]]:
    """Install pending hook hosts once each, returning skipped paths."""
    hosts = sorted({item.host for item in items if item.kind != SKILL and item.host})
    if not hosts:
        return [], [], set()
    report = hook_install.install(home, hosts=hosts, mode=mode)
    skipped = {str(entry.get("path", "")) for entry in report.get("skipped") or []}
    return list(report.get("installed") or []), list(report.get("backups") or []), skipped


def _remember(
    items: tuple[IntegrationItem, ...],
    state: SetupState,
    decision: str,
    version: str,
) -> None:
    """Record one decision per item with the current fingerprint."""
    seen_at = timestamp()
    for item in items:
        state.integration_choices[item.id] = {
            "decision": decision,
            "fingerprint": item.fingerprint,
            "version": version,
            "seen_at": seen_at,
        }


def review_pending(
    choice: SetupChoice,
    state: SetupState,
    root: Path | None,
    home: Path,
    version: str,
    read: Callable[[], str],
    write: TextIO,
    color: bool = False,
    allow_prompt: bool = True,
) -> ReviewResult:
    """Offer pending items once and apply the chosen action."""
    report = inspect(choice, state, root, home, version)
    if not report.pending:
        return ReviewResult(decision="none")
    if not allow_prompt:
        return ReviewResult(decision="pending", pending=report.pending)
    ui.render_integrations(write, _rows(report.pending, choice, root, home), color)
    try:
        action = ui.ask_integrations(write, read, color)
    except (EOFError, KeyboardInterrupt):
        return ReviewResult(decision="pending", pending=report.pending)
    if action == "install":
        backup_dir = layout.new_backup_dir(home)
        installed = _install_skills(report.pending, choice, root, home, backup_dir)
        hook_installed, hook_backups, skipped = _install_hooks(
            report.pending, home, state.effective_mode()
        )
        failed = tuple(
            item
            for item in report.pending
            if item.kind != SKILL and any(str(path) in skipped for path in hook_paths(item, home))
        )
        applied = tuple(item for item in report.pending if item not in failed)
        _remember(applied, state, "installed", version)
        hosts = sorted({item.host for item in applied if item.kind == HOOK and item.host})
        if hosts:
            state.hook_files = [
                str(spec.path) for spec in hook_install.preview(home, hosts) if spec.path.is_file()
            ]
            state.hooks_enabled = True
            state.hooks_mode = state.effective_mode()
            state.hooks = bool(state.hook_files)
        save_state(state, home)
        installed.extend(hook_installed)
        backups = [str(backup_dir)] if backup_dir.exists() else []
        backups.extend(hook_backups)
        return ReviewResult(
            decision="install",
            installed=tuple(installed),
            backups=tuple(backups),
            pending=failed,
        )
    decision = "deferred" if action == "defer" else "never"
    _remember(report.pending, state, decision, version)
    save_state(state, home)
    return ReviewResult(decision=decision)
