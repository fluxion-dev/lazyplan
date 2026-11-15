"""One panel per wizard step; the shell and apply path live in ``setup``.

Every control edits the shared :class:`SetupSession` draft. The screen host
supplies the screen lifecycle, so this module holds no writer of its own.
"""

from __future__ import annotations

from typing import Any

from ....core.policies import effort as effort_policy
from ....core.policies.agents import HOSTS, TIERS
from ....core.policies.lanes import AGENT_ROLES
from ....infrastructure import skills
from ....infrastructure.host_models import HostCatalog
from ...setup import health as setup_health
from ...setup import ui as setup_ui
from ...setup.constants import HOME
from ...setup.health import HealthFinding
from ...setup.session import SetupSession
from ...setup.steps import WELCOME, Step
from ...shared.design import escape_markup
from .setup_support import (
    HOOK_MODES,
    INHERIT,
    INHERIT_LABEL,
    INTEGRATION_CHOICES,
    TOOL_ROWS,
    Checks,
    WizardResult,
    current_line,
    review_sections,
    welcome_lines,
)

try:
    from textual.app import ComposeResult  # noqa: F401
    from textual.containers import Horizontal, Vertical  # noqa: F401
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

    from ..navigation import NavigationMixin
    from ..query import query_one_opt
    from ..theme.themes import THEME_NAMES
    from ..widgets.setup_controls import (
        host_label,
        list_block,
        note,
        row,
        widget_id,
    )

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover - stdlib-only interpreter
    _TEXTUAL_OK = False


if _TEXTUAL_OK:

    class SetupPanelsScreen(NavigationMixin, Screen[WizardResult]):
        """Panel bodies for every step, all bound to the shared draft."""

        session: SetupSession
        _checks: Checks | None
        _check_findings: tuple[HealthFinding, ...] | None
        _check_error: str
        _integration_ids: dict[str, str]

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
                fields = ", ".join(
                    f"{host} ({effort_policy.field_for(host)})" for host in supported
                )
                widgets.append(note(f"[dim]effort renders into: {escape_markup(fields)}[/]"))
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
