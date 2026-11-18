"""Wizard constants, copy, and the review plan, separate from the widgets.

The shell (``setup``) and the panels (``setup_panels``) share these values so
the step copy, apply labels, and review plan have one source of truth.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ....infrastructure import agent_install, hook_install, profiles, skills, textfile
from ....infrastructure.integrations import HOOK, SKILL, hook_paths, skill_paths
from ...setup.constants import HOME
from ...setup.health import HealthFinding
from ...setup.layout import SetupLayout
from ...setup.session import SetupSession
from ...setup.state import state_path
from ...setup.steps import (
    AGENTS,
    APPEARANCE,
    HOOKS,
    INTEGRATIONS,
    MODELS,
    PLACEMENT,
    ROLES,
    Step,
)

LATER_LABEL = "Finish later"
NEXT_LABEL = "Next"
APPLY_LABEL = "Apply"

HOOK_MODES: tuple[tuple[str, str], ...] = (
    ("strict", "Strict — hooks block unsafe commits and stops"),
    ("advisory", "Advisory — hooks remind but never block"),
    ("off", "Off — remove the managed hooks"),
)
INHERIT = "__inherit__"
INHERIT_LABEL = "inherit (host default)"
INTEGRATION_CHOICES: tuple[tuple[str, str], ...] = (
    ("install — write it now", "install"),
    ("not now — ask again next launch", "defer"),
    ("never — stop asking for this item", "never"),
)
TOOL_ROWS: tuple[tuple[str, str], ...] = (
    ("tool:lpui", "lpui on PATH"),
    ("tool:git", "git on PATH"),
    ("tool:gh", "GitHub CLI"),
    ("tool:gh-auth", "GitHub CLI login"),
)
Checks = Callable[[], tuple[HealthFinding, ...]]


@dataclass(frozen=True)
class WizardResult:
    """What one wizard run changed, for the app's restart decision."""

    applied: bool = False
    hosts: tuple[str, ...] = ()
    profiles: tuple[str, ...] = ()
    restart: bool = False
    result: dict[str, Any] = field(default_factory=dict)


def welcome_lines(session: SetupSession) -> list[str]:
    """What setup owns, where it lands, and how to leave without writing."""
    _plan, layout = session.resolved()
    lines = [
        "Setup owns the plan journal and the agent side of lazyplan:",
        f"  database   {layout.db}",
        f"  templates  {layout.templates_dir}",
    ]
    if layout.config is not None:
        lines.append(f"  config     {layout.config}")
    if layout.agents_md is not None:
        lines.append(f"  pointer    {layout.agents_md}")
    if session.draft.skills_enabled and session.draft.agents:
        lines.append("  skills     agent skill files and managed role profiles")
    lines.extend(
        [
            f"  state      {state_path(session.home)}",
            "",
            "Nothing is written until you review the last step and apply.",
            f"{LATER_LABEL} closes this screen and keeps your current setup;"
            " the wizard reopens from the palette at any time.",
        ]
    )
    return lines


def current_line(session: SetupSession, step: Step) -> str:
    """One plain-language summary of the draft for a step panel."""
    draft = session.draft
    if step.key == PLACEMENT.key:
        target = session.db_path
        return f"Plans currently live at {target} ({draft.placement} placement)."
    if step.key == AGENTS.key:
        if not draft.agents:
            return "No agent host is selected, so no skills or profiles are written."
        return f"Selected hosts: {', '.join(draft.agents)}."
    if step.key == HOOKS.key:
        pointer = "with" if draft.agents_pointer else "without"
        return f"Hooks are {draft.hooks_mode}; the AGENTS.md pointer is {pointer}."
    if step.key == MODELS.key:
        return f"{len(draft.agents)} host(s) map the fast, standard, and deep tiers."
    if step.key == ROLES.key:
        return f"{len(draft.profiles_map)} roles name a tier and an effort level."
    if step.key == INTEGRATIONS.key:
        return f"{len(session.pending)} catalog item(s) are waiting for a decision."
    if step.key == APPEARANCE.key:
        return f"Theme: {draft.theme or 'not chosen'}; icons: {draft.icons or 'not chosen'}."
    return "The next step reviews every write, removal, and state change."


def hint_text(width: int) -> str:
    """One keyboard hint line, trimmed on narrow terminals."""
    items = ["b back", "n next", "l finish later", "? help"]
    text = " · ".join(items)
    if width < 80:
        text = " · ".join(items[:3])
    return text


def review_sections(session: SetupSession) -> list[tuple[str, list[str]]]:
    """Every write, refresh, removal, and state change the draft would cause."""
    plan, resolved = session.resolved()
    groups: dict[str, list[str]] = {
        "Writes": [],
        "Refreshes": [],
        "Removals": [],
        "State changes": [],
    }
    _review_layout(session, plan, resolved, groups)
    _review_dropped_profiles(session, plan, groups)
    _review_hooks(session, groups)
    _review_pointer(session, groups)
    _review_integrations(session, plan, groups)
    groups["State changes"].extend(_review_state(session))
    return [(label, list(dict.fromkeys(items))) for label, items in groups.items() if items]


def _add_target(groups: dict[str, list[str]], path: Path | str) -> None:
    """Record one path as a write, or a refresh when it already exists."""
    text = str(path)
    key = "Refreshes" if Path(text).exists() else "Writes"
    groups[key].append(text)


def _review_layout(
    session: SetupSession,
    plan: skills.SkillPlan,
    resolved: SetupLayout,
    groups: dict[str, list[str]],
) -> None:
    """The database, templates, skills, pointer, and managed profiles."""
    draft = session.draft
    home = session.home
    _add_target(groups, resolved.db)
    _add_target(groups, resolved.templates_dir)
    if resolved.config is not None:
        _add_target(groups, resolved.config)
    for path in plan.skill_files:
        _add_target(groups, path)
    if plan.agents_md is not None:
        _add_target(groups, plan.agents_md)
    if plan.scope != "none" and draft.agents:
        _add_target(groups, profiles.path_for(resolved.db))
        for path in agent_install.profile_paths(plan.scope, session.root, home, draft.agents):
            _add_target(groups, path)


def _review_dropped_profiles(
    session: SetupSession,
    plan: skills.SkillPlan,
    groups: dict[str, list[str]],
) -> None:
    """Managed profiles for hosts the draft no longer selects."""
    state, draft = session.state, session.draft
    dropped = [host for host in state.agents if host not in draft.agents]
    scopes = {plan.scope}
    scopes.add("project" if state.placement == "repo" and session.root is not None else "global")
    for host in dropped:
        for scope in scopes:
            for path in agent_install.profile_paths(scope, session.root, session.home, [host]):
                if path.is_file() and _managed_profile(path):
                    groups["Removals"].append(str(path))


def _review_hooks(session: SetupSession, groups: dict[str, list[str]]) -> None:
    """Hook settings written for selected hosts, or removed when off."""
    draft, state = session.draft, session.state
    hosts = sorted(set(draft.agents) | set(state.agents))
    specs = hook_install.preview(
        session.home,
        [host for host in hosts if host in hook_install.HOSTS],
    )
    if draft.hooks_mode == "off":
        for spec in specs:
            if spec.path.is_file():
                groups["Removals"].append(str(spec.path))
        return
    for spec in specs:
        if spec.host in draft.agents:
            _add_target(groups, spec.path)


def _review_pointer(session: SetupSession, groups: dict[str, list[str]]) -> None:
    """The opt-in AGENTS.md pointer for home placement."""
    draft, state = session.draft, session.state
    pointer = session.root / "AGENTS.md" if session.root is not None else None
    if pointer is None:
        return
    if draft.agents_pointer and draft.placement == HOME:
        _add_target(groups, pointer)
    elif state.agents_pointer and pointer.is_file():
        groups["Removals"].append(str(pointer))


def _review_integrations(
    session: SetupSession,
    plan: skills.SkillPlan,
    groups: dict[str, list[str]],
) -> None:
    """Pending skills and hooks that install now, or the decision to remember."""
    draft = session.draft
    for item in session.pending:
        decision = draft.integrations.get(item.id, "install")
        if decision != "install":
            groups["State changes"].append(f"integration {item.label}: {decision}")
            continue
        if item.kind == SKILL and plan.scope != "none":
            paths = skill_paths(
                item,
                plan.scope,
                session.root,
                session.home,
                plan.tools,
                plan.skills_dir,
            )
            for path in paths:
                _add_target(groups, path)
        elif item.kind == HOOK:
            for path in hook_paths(item, session.home):
                _add_target(groups, path)


def _review_state(session: SetupSession) -> list[str]:
    """The setup state fields this run changes."""
    state, draft = session.state, session.draft
    theme = (
        f"theme: {state.theme or 'default'} -> {draft.theme}"
        if draft.theme and draft.theme != state.theme
        else f"theme: unchanged ({state.theme or 'default'})"
    )
    icons = (
        f"icons: {state.icons or 'default'} -> {draft.icons}"
        if draft.icons and draft.icons != state.icons
        else f"icons: unchanged ({state.icons or 'default'})"
    )
    return [
        f"setup state: {state_path(session.home)}",
        f"placement: {state.placement} -> {draft.placement}",
        f"agents: {', '.join(state.agents) or 'none'} -> {', '.join(draft.agents) or 'none'}",
        f"hooks: {state.effective_mode()} -> {draft.hooks_mode}",
        f"AGENTS.md pointer: {'on' if draft.agents_pointer else 'off'}",
        theme,
        icons,
        "pending wizard marker: cleared for this version",
    ]


def _managed_profile(path: Any) -> bool:
    """True when the file carries lazyplan's managed marker."""
    try:
        return agent_install.MARKER in textfile.read(path)
    except OSError:
        return False
