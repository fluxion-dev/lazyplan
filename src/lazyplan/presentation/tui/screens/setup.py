"""Full-screen setup wizard: steps, controls, review, and apply.

The screen is a second front end for :class:`SetupSession`; it never writes
outside ``session.apply``. Panels edit the session draft, the rail moves
between steps, and dismissal reports exactly what the app should restart.
"""

from __future__ import annotations

import copy
import io
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ....core.policies import effort as effort_policy
from ....core.policies.agents import DEFAULT_ROLE_TIERS, HOSTS, TIERS
from ....core.policies.hooks import MODES
from ....core.policies.lanes import AGENT_ROLES
from ....infrastructure import agent_install, hook_install, profiles, skills, textfile
from ....infrastructure.host_models import HostCatalog
from ....infrastructure.integrations import HOOK, SKILL, hook_paths, skill_paths
from ...setup import health as setup_health
from ...setup import ui as setup_ui
from ...setup.constants import HOME
from ...setup.health import HealthFinding
from ...setup.layout import resolve_choice
from ...setup.session import SetupSession, SetupSessionError
from ...setup.state import state_path
from ...setup.steps import WELCOME, Step
from ...shared.design import escape_markup

try:
    from textual import events, on
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.screen import Screen
    from textual.widgets import (
        Button,
        Checkbox,
        Input,
        Label,
        OptionList,
        Select,
        Static,
    )
    from textual.widgets.option_list import Option

    from ..navigation import NAV_BINDINGS, NavigationMixin
    from ..query import query_one_opt
    from ..theme.themes import THEME_NAMES
    from ..widgets.setup_controls import (
        first_focusable,
        host_label,
        list_block,
        note,
        row,
        widget_id,
    )

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover - stdlib-only interpreter
    _TEXTUAL_OK = False

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
    choice = session.choice()
    plan = skills.plan_choice(choice, session.root, session.home)
    layout = resolve_choice(choice, session.root, plan, session.home)
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
    if step.key == "placement":
        target = session.db_path
        return f"Plans currently live at {target} ({draft.placement} placement)."
    if step.key == "agents":
        if not draft.agents:
            return "No agent host is selected, so no skills or profiles are written."
        return f"Selected hosts: {', '.join(draft.agents)}."
    if step.key == "hooks":
        pointer = "with" if draft.agents_pointer else "without"
        return f"Hooks are {draft.hooks_mode}; the AGENTS.md pointer is {pointer}."
    if step.key == "models":
        return f"{len(draft.agents)} host(s) map the fast, standard, and deep tiers."
    if step.key == "roles":
        return f"{len(draft.profiles_map)} roles name a tier and an effort level."
    if step.key == "integrations":
        return f"{len(session.pending)} catalog item(s) are waiting for a decision."
    if step.key == "appearance":
        return f"Theme: {draft.theme or 'not chosen'}."
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
    draft = session.draft
    state = session.state
    home = session.home
    root = session.root
    choice = session.choice()
    plan = skills.plan_choice(choice, root, home)
    resolved = resolve_choice(choice, root, plan, home)
    groups: dict[str, list[str]] = {
        "Writes": [],
        "Refreshes": [],
        "Removals": [],
        "State changes": [],
    }

    def add(path: Path | str) -> None:
        text = str(path)
        if Path(text).exists():
            groups["Refreshes"].append(text)
        else:
            groups["Writes"].append(text)

    add(resolved.db)
    add(resolved.templates_dir)
    if resolved.config is not None:
        add(resolved.config)
    for path in plan.skill_files:
        add(path)
    if plan.agents_md is not None:
        add(plan.agents_md)
    if plan.scope != "none" and draft.agents:
        add(profiles.path_for(resolved.db))
        for path in agent_install.profile_paths(plan.scope, root, home, draft.agents):
            add(path)
    dropped = [host for host in state.agents if host not in draft.agents]
    scopes = {plan.scope}
    scopes.add("project" if state.placement == "repo" and root is not None else "global")
    for host in dropped:
        for scope in scopes:
            for path in agent_install.profile_paths(scope, root, home, [host]):
                if path.is_file() and _managed_profile(path):
                    groups["Removals"].append(str(path))
    hosts = sorted(set(draft.agents) | set(state.agents))
    specs = hook_install.preview(home, [host for host in hosts if host in hook_install.HOSTS])
    if draft.hooks_mode == "off":
        for spec in specs:
            if spec.path.is_file():
                groups["Removals"].append(str(spec.path))
    else:
        for spec in specs:
            if spec.host in draft.agents:
                add(spec.path)
    pointer = root / "AGENTS.md" if root is not None else None
    if pointer is not None and draft.agents_pointer and draft.placement == HOME:
        add(pointer)
    elif pointer is not None and state.agents_pointer and pointer.is_file():
        groups["Removals"].append(str(pointer))
    for item in session.pending:
        decision = draft.integrations.get(item.id, "install")
        if decision != "install":
            groups["State changes"].append(f"integration {item.label}: {decision}")
            continue
        if item.kind == SKILL and plan.scope != "none":
            for path in skill_paths(item, plan.scope, root, home, plan.tools, plan.skills_dir):
                add(path)
        elif item.kind == HOOK:
            for path in hook_paths(item, home):
                add(path)
    theme = (
        f"theme: {state.theme or 'default'} -> {draft.theme}"
        if draft.theme and draft.theme != state.theme
        else f"theme: unchanged ({state.theme or 'default'})"
    )
    groups["State changes"].extend(
        [
            f"setup state: {state_path(home)}",
            f"placement: {state.placement} -> {draft.placement}",
            f"agents: {', '.join(state.agents) or 'none'} -> {', '.join(draft.agents) or 'none'}",
            f"hooks: {state.effective_mode()} -> {draft.hooks_mode}",
            f"AGENTS.md pointer: {'on' if draft.agents_pointer else 'off'}",
            theme,
            "pending wizard marker: cleared for this version",
        ]
    )
    return [(label, list(dict.fromkeys(items))) for label, items in groups.items() if items]


def _managed_profile(path: Any) -> bool:
    """True when the file carries lazyplan's managed marker."""
    try:
        return agent_install.MARKER in textfile.read(path)
    except OSError:
        return False


if _TEXTUAL_OK:

    class SetupWizardScreen(NavigationMixin, Screen[WizardResult]):
        """Multi-step setup: one panel per step, one shared draft.

        Push it with a loaded session and an optional step key. The dismiss
        payload is always a :class:`WizardResult`; ``applied`` is false when
        the user cancelled or finished later, and nothing was written.
        """

        navigation_name = "setup"

        BINDINGS = [
            *NAV_BINDINGS,
            Binding("escape", "cancel", LATER_LABEL, priority=True),
            Binding("b", "previous", "Back"),
            Binding("n", "next", NEXT_LABEL),
            Binding("l", "later", LATER_LABEL),
        ]

        def __init__(
            self,
            session: SetupSession,
            start: str = "",
            *,
            checks: Checks | None = None,
        ) -> None:
            super().__init__()
            self.session = session
            self._steps = session.steps()
            self._index = self._start_index(start)
            self._initial = copy.deepcopy(session.draft)
            self._initial_theme = ""
            self._checks = checks
            self._check_findings: tuple[HealthFinding, ...] | None = None
            self._check_error = ""
            self._integration_ids: dict[str, str] = {}
            self._errors: tuple[str, ...] = ()
            self._applying = False
            self._apply_error = ""
            self._result: WizardResult | None = None

        def _start_index(self, start: str) -> int:
            """The requested step when it is visible, else the first one."""
            keys = [step.key for step in self._steps]
            if start in keys:
                return keys.index(start)
            return 0

        @property
        def step(self) -> Step:
            """The step on screen."""
            return self._steps[self._index]

        def compose(self) -> ComposeResult:
            with Vertical(id="setup-page"):
                with Vertical(id="setup-head"):
                    yield Label("", id="setup-counter")
                    yield Label("", id="setup-step-title")
                    yield Static("", id="setup-copy")
                with Horizontal(id="setup-main"):
                    with VerticalScroll(id="setup-rail"):
                        yield OptionList(id="setup-rail-list")
                    with VerticalScroll(id="setup-content"):
                        with Vertical(id="setup-panel"):
                            yield from self._panel_widgets(self.step)
                yield Static("", id="setup-errors")
                yield Label("", id="setup-hints")
                with Horizontal(id="setup-actions"):
                    yield Button("Back", id="setup-back")
                    yield Button(NEXT_LABEL, id="setup-next", variant="primary")
                    yield Button(LATER_LABEL, id="setup-later")

        def on_mount(self) -> None:
            self._apply_size(self.app.size.width, self.app.size.height)
            self._initial_theme = str(getattr(self.app, "theme", ""))
            page = self.query_one("#setup-page")
            page.border_title = " setup "
            self._fill_rail()
            self._update_chrome()
            self.call_after_refresh(self._focus_panel)
            if self.step.key == "appearance":
                self.call_after_refresh(self._start_checks)

        def _apply_size(self, width: int, height: int) -> None:
            """Mirror the shell's compact, wide, and short size classes."""
            self.set_class(width < 80, "compact")
            self.set_class(width >= 120, "wide")
            self.set_class(height < 30, "short")
            hints = query_one_opt(self, "#setup-hints", Label)
            if hints is not None:
                hints.update(hint_text(width))

        def on_resize(self, event: events.Resize) -> None:
            self._apply_size(event.size.width, event.size.height)

        def _fill_rail(self) -> None:
            """Label every visible step and highlight the current one."""
            rail = query_one_opt(self, "#setup-rail-list", OptionList)
            if rail is None:
                return
            rail.clear_options()
            rail.add_options([Option(step.title, id=step.key) for step in self._steps])
            rail.highlighted = self._index

        def _update_chrome(self) -> None:
            """Refresh the counter, copy, rail, and action buttons."""
            total = len(self._steps)
            self.query_one("#setup-counter", Label).update(f"Step {self._index + 1} of {total}")
            self.query_one("#setup-step-title", Label).update(escape_markup(self.step.title))
            self.query_one("#setup-copy", Static).update(escape_markup(self.step.summary))
            rail = query_one_opt(self, "#setup-rail-list", OptionList)
            if rail is not None and rail.highlighted != self._index:
                rail.highlighted = self._index
            self.query_one("#setup-back", Button).disabled = self._index == 0
            self._show_errors()
            self._update_primary()

        def _update_primary(self) -> None:
            """One primary button: Next, Apply, or Close after applying."""
            button = self.query_one("#setup-next", Button)
            last = self._index == len(self._steps) - 1
            if self._result is not None:
                button.label = "Close"
                button.disabled = False
            else:
                button.label = APPLY_LABEL if last else NEXT_LABEL
                button.disabled = self._applying
            back = self.query_one("#setup-back", Button)
            back.disabled = self._index == 0 or self._applying or self._result is not None
            later = self.query_one("#setup-later", Button)
            later.disabled = self._applying and self._result is None

        def _show_errors(self) -> None:
            block = self.query_one("#setup-errors", Static)
            block.display = bool(self._errors)
            block.update("\n".join(f"[red]✗[/] {escape_markup(error)}" for error in self._errors))

        def _panel_widgets(self, step: Step) -> list[Any]:
            """The body of one step, wired to the shared session draft."""
            builders = {
                WELCOME.key: self._welcome_panel,
                "placement": self._placement_panel,
                "agents": self._agents_panel,
                "hooks": self._hooks_panel,
                "models": self._models_panel,
                "roles": self._roles_panel,
                "integrations": self._integrations_panel,
                "appearance": self._appearance_panel,
                "review": self._review_panel,
            }
            builder = builders.get(step.key)
            if builder is not None:
                return builder()
            return [
                Static(
                    escape_markup(current_line(self.session, step)),
                    id="setup-current",
                )
            ]

        def _welcome_panel(self) -> list[Any]:
            return [
                Static(
                    "\n".join(welcome_lines(self.session)),
                    id="setup-welcome",
                    markup=False,
                )
            ]

        def _placement_panel(self) -> list[Any]:
            """Home and repo placement, each with its exact target and tradeoff."""
            draft = self.session.draft
            choices = setup_ui.placement_choices(self.session.root, self.session.home)
            options = [Option(f"{label} — {path}", id=key) for key, label, path, _note in choices]
            widgets: list[Any] = [
                OptionList(*options, id="setup-placement-list"),
                note(
                    "Choose where the plan journal lives. Both choices keep the"
                    " database out of version control when it sits in a checkout."
                ),
            ]
            for _key, label, path, tradeoff in choices:
                widgets.append(
                    Static(
                        f"[b]{escape_markup(label)}[/] [dim]{escape_markup(str(path))}[/]\n"
                        f"{escape_markup(tradeoff)}",
                        classes="setup-choice",
                    )
                )
            widgets.append(note(f"Current: {draft.placement}"))
            return widgets

        def _agents_panel(self) -> list[Any]:
            """Detected hosts with their hint and the skill toggle."""
            draft = self.session.draft
            detected = {host.key: host for host in skills.detect_agents(self.session.home)}
            widgets: list[Any] = [
                note(
                    "Selected hosts receive the lazyplan skill and managed role"
                    " profiles. Detection is local and read-only."
                )
            ]
            for host in HOSTS:
                found = detected.get(host)
                if found is None:
                    label = host
                elif found.detected:
                    label = f"{found.label} — detected ({found.hint})"
                else:
                    label = f"{found.label} — not detected ({found.hint})"
                widgets.append(
                    Checkbox(
                        label,
                        value=host in draft.agents,
                        compact=True,
                        id=f"setup-agent-{host}",
                    )
                )
            widgets.append(
                Checkbox(
                    "Install the managed skills and role profiles",
                    value=draft.skills_enabled,
                    compact=True,
                    id="setup-skills",
                )
            )
            widgets.append(
                note(
                    "Turning skills off leaves the hosts selected but writes no"
                    " skill files, profiles, or model map."
                )
            )
            return widgets

        def _hooks_panel(self) -> list[Any]:
            """Hook mode, its tradeoffs, and the opt-in AGENTS.md pointer."""
            draft = self.session.draft
            pointer_ready = self.session.root is not None and draft.placement == HOME
            widgets: list[Any] = [
                Label("Hook mode", classes="setup-label"),
                Select(
                    [(label, key) for key, label in HOOK_MODES],
                    value=draft.hooks_mode,
                    allow_blank=False,
                    id="setup-hooks-mode",
                ),
                note(
                    "Hooks record agent sessions, inject the active plan, and check"
                    " commits and stops. Off removes the managed hooks and asks for"
                    " no session tracking."
                ),
                Checkbox(
                    "Add the lazyplan pointer to this checkout's AGENTS.md",
                    value=draft.agents_pointer and pointer_ready,
                    compact=True,
                    id="setup-pointer",
                    disabled=not pointer_ready,
                ),
                note(
                    "The pointer names the shared database so agents in this"
                    " checkout know where the plans live."
                    if pointer_ready
                    else "The pointer applies only with home placement in a git"
                    " checkout; repo placement sets it up with the repo resources."
                ),
            ]
            return widgets

        def _models_panel(self) -> list[Any]:
            """One tier target per selected host, with catalog options and manual entry."""
            draft = self.session.draft
            widgets: list[Any] = [
                note(
                    "Each host maps the fast, standard, and deep tiers to one of its"
                    " own models. Type any model id the host accepts, or leave a"
                    " target empty to inherit the host's configured default."
                )
            ]
            for host in draft.agents:
                catalog = self.session.catalogs.get(host)
                label = catalog.label if catalog is not None else host.title()
                widgets.append(host_label(f"[b]{escape_markup(label)}[/]"))
                if catalog is not None:
                    source = catalog.source or "defaults"
                    widgets.append(note(f"[dim]source: {escape_markup(source)}[/]"))
                    if catalog.warning:
                        widgets.append(note(f"[yellow]{escape_markup(catalog.warning)}[/]"))
                for tier in TIERS:
                    current = str((draft.tiers_map.get(tier) or {}).get(host, "") or "").strip()
                    widgets.append(
                        row(
                            tier,
                            Select(
                                self._model_options(catalog, current),
                                value=current or INHERIT,
                                allow_blank=False,
                                id=f"setup-tier-{host}-{tier}",
                            ),
                            Input(
                                value=current,
                                placeholder="model id, empty for inherit",
                                id=f"setup-model-{host}-{tier}",
                            ),
                        )
                    )
            return widgets

        @staticmethod
        def _model_options(catalog: HostCatalog | None, current: str) -> list[tuple[str, str]]:
            """Catalog models plus inherit, keeping a manual id visible."""
            models = list(catalog.models) if catalog is not None else []
            values = [INHERIT, *models]
            if current and current not in models:
                values.insert(1, current)
            return [(INHERIT_LABEL if value == INHERIT else value, value) for value in values]

        def _roles_panel(self) -> list[Any]:
            """One tier and curated effort selector per role, plus a reset."""
            draft = self.session.draft
            supported = [host for host in draft.agents if effort_policy.supports(host)]
            widgets: list[Any] = [
                note(
                    "Every role names a capability tier and an optional effort"
                    " level. Effort is written only into hosts that have a native"
                    " field; every other host stays at inherit."
                )
            ]
            if not supported:
                widgets.append(
                    note(
                        "None of the selected hosts has an effort field, so the"
                        " effort selectors are disabled and roles stay at inherit."
                    )
                )
            else:
                widgets.append(
                    note(f"[dim]effort renders into: {escape_markup(', '.join(supported))}[/]")
                )
            for role in AGENT_ROLES:
                profile = draft.profiles_map.get(role)
                if profile is None:
                    continue
                stored = effort_policy.normalize(profile.effort)
                level = stored if stored in effort_policy.LEVELS else effort_policy.INHERIT
                widgets.append(
                    row(
                        role,
                        Select(
                            [(tier, tier) for tier in TIERS],
                            value=profile.tier if profile.tier in TIERS else "standard",
                            allow_blank=False,
                            id=f"setup-role-tier-{role}",
                        ),
                        Select(
                            [
                                (effort_policy.LABELS[value], value)
                                for value in effort_policy.LEVELS
                            ],
                            value=level,
                            allow_blank=False,
                            disabled=not supported,
                            id=f"setup-role-effort-{role}",
                        ),
                    )
                )
                if profile.effort and stored not in effort_policy.LEVELS:
                    widgets.append(
                        note(
                            f"[yellow]{escape_markup(role)} keeps the stored effort"
                            f" {escape_markup(profile.effort)} until you choose a"
                            " level; choosing inherit clears it.[/]"
                        )
                    )
            widgets.append(Button("Reset roles to tier defaults", id="setup-roles-reset"))
            return widgets

        def _integrations_panel(self) -> list[Any]:
            """One install, not now, or never decision per pending item."""
            draft = self.session.draft
            widgets: list[Any] = [
                note(
                    "A release can add a skill or hook surface. Install writes it"
                    " now; not now asks again next launch; never stops asking for"
                    " this exact item."
                )
            ]
            if not self.session.pending:
                widgets.append(note("Nothing is pending right now."))
                return widgets
            for item in self.session.pending:
                ident = widget_id(item.id)
                self._integration_ids[ident] = item.id
                widgets.append(
                    Static(
                        f"[b]{escape_markup(item.label)}[/] [dim]{escape_markup(item.kind)}[/]",
                        classes="setup-item",
                    )
                )
                widgets.append(
                    Select(
                        list(INTEGRATION_CHOICES),
                        value=draft.integrations.get(item.id, "install"),
                        allow_blank=False,
                        id=f"setup-integration-{ident}",
                    )
                )
            return widgets

        def _appearance_panel(self) -> list[Any]:
            """Theme preview plus read-only tool and GitHub login checks."""
            theme = self._theme_value()
            widgets: list[Any] = [
                Label("Theme", classes="setup-label"),
                Select(
                    [
                        (
                            name.removeprefix("lazyplan-").replace("-", " ").title(),
                            name,
                        )
                        for name in THEME_NAMES
                    ],
                    value=theme,
                    allow_blank=False,
                    id="setup-theme",
                ),
                note(
                    "The preview applies immediately and is remembered when you"
                    " apply. LAZYPLAN_THEME still wins over the remembered choice."
                ),
                Label("Checks", classes="setup-label"),
                Static(self._checks_text(), id="setup-checks-body", classes="setup-checks"),
                Button("Recheck", id="setup-recheck"),
                note(
                    "The checks are read-only. They name the missing tool or login"
                    " and the command that fixes it; the wizard never asks for or"
                    " stores a token."
                ),
            ]
            return widgets

        def _theme_value(self) -> str:
            """The theme the picker shows: remembered, else the live app theme."""
            draft = self.session.draft
            if draft.theme in THEME_NAMES:
                return draft.theme
            live = str(getattr(self.app, "theme", ""))
            return live if live in THEME_NAMES else THEME_NAMES[0]

        def _checks_text(self) -> str:
            """One line per tool, with the fix for anything missing."""
            if self._check_error:
                return f"[red]The check could not run:[/] {escape_markup(self._check_error)}"
            if self._check_findings is None:
                return "Checking lpui, git, GitHub CLI, and GitHub login…"
            found = {finding.id: finding for finding in self._check_findings}
            lines: list[str] = []
            for key, label in TOOL_ROWS:
                finding = found.get(key)
                if finding is not None:
                    mark = "[red]✗[/]" if finding.severity == setup_health.ERROR else "[yellow]![/]"
                    lines.append(f"{mark} [b]{escape_markup(label)}[/]")
                    lines.append(f"  {escape_markup(finding.capability)}")
                    if finding.fix:
                        lines.append(f"  [dim]fix:[/] {escape_markup(finding.fix)}")
                elif key == "tool:gh-auth" and "tool:gh" in found:
                    lines.append("[dim]– GitHub CLI login is skipped until gh is installed[/]")
                else:
                    lines.append(f"[green]✓[/] {escape_markup(label)} — ok")
            return "\n".join(lines)

        def _start_checks(self) -> None:
            """Run the read-only checks off the UI thread."""
            body = query_one_opt(self, "#setup-checks-body", Static)
            if body is not None:
                body.update(self._checks_text())
            self.run_worker(self._check_worker, thread=True, exclusive=True, group="setup-checks")

        def _findings(self) -> tuple[HealthFinding, ...]:
            """Tool findings from the injected check or the live probes."""
            if self._checks is not None:
                return tuple(self._checks())
            report = setup_health.check(
                self.session.choice(),
                self.session.state,
                self.session.root,
                self.session.home,
                self.session.version,
            )
            wanted = {key for key, _label in TOOL_ROWS}
            return tuple(finding for finding in report.findings if finding.id in wanted)

        def _check_worker(self) -> None:
            try:
                findings = self._findings()
            except Exception as exc:  # noqa: BLE001 - show the failure on the step
                self.app.call_from_thread(self._checks_done, (), str(exc))
            else:
                self.app.call_from_thread(self._checks_done, findings, "")

        def _checks_done(self, findings: tuple[HealthFinding, ...], error: str) -> None:
            if not self.is_mounted:
                return
            self._check_findings = findings
            self._check_error = error
            body = query_one_opt(self, "#setup-checks-body", Static)
            if body is not None:
                body.update(self._checks_text())

        def _review_panel(self) -> list[Any]:
            """Exact writes, refreshes, removals, and state changes."""
            widgets: list[Any] = [
                note(
                    "Apply writes these exact files through the same setup path as"
                    " `lpui setup`. Nothing has been written yet."
                )
            ]
            for label, items in review_sections(self.session):
                widgets.append(host_label(f"[b]{label}[/]"))
                widgets.append(list_block([escape_markup(item) for item in items]))
            widgets.append(Static("", id="setup-apply-status", classes="setup-apply-status"))
            return widgets

        def _set_apply_status(self, text: str) -> None:
            status = query_one_opt(self, "#setup-apply-status", Static)
            if status is not None:
                status.update(text)
                status.display = bool(text)

        def _start_apply(self) -> None:
            """Validate, then run the shared apply path off the UI thread."""
            if self._applying or self._result is not None:
                return
            self._commit_inputs()
            self._errors = tuple(self.session.validate())
            if self._errors:
                self._update_chrome()
                return
            self._applying = True
            self._apply_error = ""
            self._update_chrome()
            self._set_apply_status("[yellow]Applying setup…[/]")
            self.run_worker(self._apply_worker, thread=True, exclusive=True, group="setup-apply")

        def _apply_worker(self) -> None:
            try:
                result = self.session.apply(io.StringIO())
            except Exception as exc:  # noqa: BLE001 - keep the failure on the step
                self.app.call_from_thread(self._apply_failed, str(exc))
            else:
                self.app.call_from_thread(self._apply_done, result)

        def _apply_done(self, result: dict[str, Any]) -> None:
            """Keep the summary on the step and wait for Close."""
            if not self.is_mounted:
                return
            self._applying = False
            profiles = tuple(
                str(path)
                for path in [
                    *(result.get("profile_files") or []),
                    *(result.get("removed_profiles") or []),
                ]
            )
            hooks = result.get("hooks") or {}
            restart = bool(
                hooks.get("installed")
                or hooks.get("backups")
                or result.get("installed")
                or profiles
            )
            self._result = WizardResult(
                applied=True,
                hosts=tuple(result.get("agents") or ()),
                profiles=profiles,
                restart=restart,
                result=dict(result),
            )
            tail = (
                " Restart running agent sessions; their skills or hooks changed." if restart else ""
            )
            self._set_apply_status(f"[green]Setup applied.[/] Press Close to return.{tail}")
            self._update_chrome()

        def _apply_failed(self, detail: str) -> None:
            """Leave the wizard open and name the failure."""
            if not self.is_mounted:
                return
            self._applying = False
            self._apply_error = detail
            self._set_apply_status(
                f"[red]Apply failed[/]\n{escape_markup(detail)}\n"
                "The previous setup is unchanged. Fix the problem and apply again."
            )
            self._update_chrome()

        async def _show_step(self) -> None:
            """Swap the panel for the step now selected."""
            panel = self.query_one("#setup-panel", Vertical)
            await panel.remove_children()
            await panel.mount(*self._panel_widgets(self.step))
            self._update_chrome()
            self._highlight_panel_choice()
            self.call_after_refresh(self._focus_panel)
            if self.step.key == "appearance":
                self.call_after_refresh(self._start_checks)

        def _highlight_panel_choice(self) -> None:
            """Highlight the remembered placement in its option list."""
            listing = query_one_opt(self, "#setup-placement-list", OptionList)
            if listing is None:
                return
            keys = [
                str(option.id)
                for option in (listing.get_option_at_index(i) for i in range(listing.option_count))
            ]
            if self.session.draft.placement in keys:
                listing.highlighted = keys.index(self.session.draft.placement)

        def _sync_steps(self) -> None:
            """Keep the rail in step with visibility changes in the draft."""
            steps = self.session.steps()
            if tuple(step.key for step in steps) == tuple(step.key for step in self._steps):
                self._steps = steps
                return
            current = self.step.key
            self._steps = steps
            keys = [step.key for step in steps]
            self._index = (
                keys.index(current) if current in keys else min(self._index, len(steps) - 1)
            )
            self._fill_rail()

        def _after_change(self) -> None:
            """Re-sync the rail and chrome after a draft edit."""
            self._sync_steps()
            self._update_chrome()

        def _focus_panel(self) -> None:
            """Focus the first control in the panel, or the Next button."""
            panel = query_one_opt(self, "#setup-panel")
            if panel is not None:
                first = first_focusable(panel)
                if first is not None:
                    first.focus()
                    return
            button = query_one_opt(self, "#setup-next", Button)
            if button is not None and not button.disabled:
                button.focus()

        async def _select(self, index: int) -> None:
            if not 0 <= index < len(self._steps) or index == self._index:
                return
            self._index = index
            await self._show_step()

        def _dirty(self) -> bool:
            return self.session.draft != self._initial

        def _commit_inputs(self) -> None:
            """Adopt typed model ids before leaving a step."""
            for widget in self.query(Input):
                ident = widget.id or ""
                if not ident.startswith("setup-model-"):
                    continue
                host, _, tier = ident.removeprefix("setup-model-").rpartition("-")
                if host and tier:
                    self.session.set_tier_model(host, tier, widget.value.strip())

        async def action_previous(self) -> None:
            """Move one step back; edits stay in the draft."""
            if self._applying or self._result is not None:
                return
            self._commit_inputs()
            await self._select(self._index - 1)

        async def action_next(self) -> None:
            """Close after applying, apply on the last step, else move forward."""
            if self._applying:
                return
            if self._result is not None:
                self.dismiss(self._result)
                return
            self._commit_inputs()
            self._errors = tuple(self.session.validate())
            if self._errors:
                self._update_chrome()
                return
            if self._index == len(self._steps) - 1:
                self._start_apply()
                return
            await self._select(self._index + 1)

        def action_later(self) -> None:
            """Close without writing anything, returning the applied result."""
            if self._applying:
                return
            if self._result is not None:
                self.dismiss(self._result)
                return
            self._restore_theme()
            self.dismiss(WizardResult())

        def _restore_theme(self) -> None:
            """Put the preview back when the run ends without applying."""
            if self._initial_theme and getattr(self.app, "theme", "") != self._initial_theme:
                self.app.theme = self._initial_theme

        def action_cancel(self) -> None:
            """Ask before discarding edits, then close without writing."""
            if self._applying:
                return
            if self._result is not None:
                self.dismiss(self._result)
                return
            if not self._dirty():
                self._restore_theme()
                self.dismiss(WizardResult())
                return
            from .forms import ConfirmScreen

            def cb(confirmed: bool | None) -> None:
                if confirmed:
                    self._restore_theme()
                    self.dismiss(WizardResult())

            self.app.push_screen(
                ConfirmScreen(
                    "Discard these setup changes? Nothing has been written.",
                    confirm_label="Discard",
                    variant="warning",
                ),
                cb,
            )

        @on(OptionList.OptionSelected, "#setup-rail-list")
        async def _rail_selected(self, event: OptionList.OptionSelected) -> None:
            event.stop()
            keys = [step.key for step in self._steps]
            if event.option.id in keys:
                await self._select(keys.index(str(event.option.id)))

        @on(OptionList.OptionSelected, "#setup-placement-list")
        async def _placement_selected(self, event: OptionList.OptionSelected) -> None:
            event.stop()
            try:
                self.session.set_placement(str(event.option.id))
            except SetupSessionError as exc:
                self.notify(str(exc), severity="error")
                return
            self._after_change()
            await self._show_step()

        @on(Checkbox.Changed)
        def _checkbox_changed(self, event: Checkbox.Changed) -> None:
            """Apply one host, skills, or pointer toggle to the draft."""
            ident = event.checkbox.id or ""
            if ident == "setup-skills":
                self.session.set_skills_enabled(bool(event.value))
            elif ident == "setup-pointer":
                self.session.draft.agents_pointer = bool(event.value)
            elif ident.startswith("setup-agent-"):
                self.session.set_agents(self._selected_hosts())
            else:
                return
            self._after_change()

        def _selected_hosts(self) -> list[str]:
            """Hosts whose checkbox is on, in registry order."""
            chosen: list[str] = []
            for host in HOSTS:
                box = query_one_opt(self, f"#setup-agent-{host}", Checkbox)
                if box is not None and box.value:
                    chosen.append(host)
            return chosen

        @on(Select.Changed, "#setup-hooks-mode")
        def _hooks_changed(self, event: Select.Changed) -> None:
            mode = str(event.value)
            if mode not in MODES:
                return
            self.session.set_hooks_mode(mode)
            self._after_change()

        @on(Select.Changed)
        def _select_changed(self, event: Select.Changed) -> None:
            """Route tier and role selectors to the session mutators."""
            ident = event.select.id or ""
            value = str(event.value)
            if ident.startswith("setup-tier-"):
                host, _, tier = ident.removeprefix("setup-tier-").rpartition("-")
                model = "" if value == INHERIT else value
                if host and tier:
                    self.session.set_tier_model(host, tier, model)
                    entry = query_one_opt(self, f"#setup-model-{host}-{tier}", Input)
                    if entry is not None:
                        entry.value = model
            elif ident.startswith("setup-role-tier-"):
                self.session.set_role_tier(ident.removeprefix("setup-role-tier-"), value)
            elif ident.startswith("setup-role-effort-"):
                self.session.set_role_effort(ident.removeprefix("setup-role-effort-"), value)
            elif ident.startswith("setup-integration-"):
                item_id = self._integration_ids.get(ident.removeprefix("setup-integration-"))
                if item_id is not None:
                    self.session.set_integration(item_id, value)

        @on(Select.Changed, "#setup-theme")
        def _theme_changed(self, event: Select.Changed) -> None:
            """Preview a theme and remember the choice in the draft."""
            name = str(event.value)
            if name in THEME_NAMES:
                self.session.draft.theme = name
                self.app.theme = name

        @on(Button.Pressed, "#setup-recheck")
        def _recheck(self) -> None:
            self._check_findings = None
            self._check_error = ""
            self._start_checks()

        @on(Input.Submitted)
        def _model_submitted(self, event: Input.Submitted) -> None:
            """Store a manually typed model id and mirror it in the selector."""
            ident = event.input.id or ""
            if not ident.startswith("setup-model-"):
                return
            host, _, tier = ident.removeprefix("setup-model-").rpartition("-")
            if not host or not tier:
                return
            model = event.value.strip()
            self.session.set_tier_model(host, tier, model)
            catalog = self.session.catalogs.get(host)
            known = not model or (catalog is not None and model in catalog.models)
            selector = query_one_opt(self, f"#setup-tier-{host}-{tier}", Select)
            if known and selector is not None:
                selector.value = model or INHERIT

        @on(Button.Pressed, "#setup-roles-reset")
        async def _reset_roles(self) -> None:
            """Return every role to its packaged tier and inherited effort."""
            for role in self.session.draft.profiles_map:
                self.session.set_role_tier(role, DEFAULT_ROLE_TIERS.get(role, "standard"))
                self.session.set_role_effort(role, effort_policy.INHERIT)
            self._update_chrome()
            await self._show_step()

        @on(Button.Pressed, "#setup-back")
        async def _back(self) -> None:
            await self.action_previous()

        @on(Button.Pressed, "#setup-next")
        async def _next(self) -> None:
            await self.action_next()

        @on(Button.Pressed, "#setup-later")
        def _later(self) -> None:
            self.action_later()
