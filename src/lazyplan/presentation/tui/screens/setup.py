"""Full-screen setup wizard: steps, controls, review, and apply.

The screen is a second front end for :class:`SetupSession`; it never writes
outside ``session.apply``. Panels edit the session draft, the rail moves
between steps, and dismissal reports exactly what the app should restart.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from ....core.policies import effort as effort_policy
from ....core.policies.agents import DEFAULT_ROLE_TIERS, HOSTS, TIERS
from ....core.policies.hooks import MODES
from ....core.policies.lanes import AGENT_ROLES
from ....infrastructure import skills
from ....infrastructure.host_models import HostCatalog
from ...setup import ui as setup_ui
from ...setup.constants import HOME
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


def _first_focusable(node: Any) -> Any:
    """The first widget in *node* that can take focus, depth first."""
    for child in getattr(node, "children", ()):
        if getattr(child, "can_focus", False) and not getattr(child, "disabled", False):
            return child
        found = _first_focusable(child)
        if found is not None:
            return found
    return None


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

        def __init__(self, session: SetupSession, start: str = "") -> None:
            super().__init__()
            self.session = session
            self._steps = session.steps()
            self._index = self._start_index(start)
            self._initial = copy.deepcopy(session.draft)
            self._errors: tuple[str, ...] = ()

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
            page = self.query_one("#setup-page")
            page.border_title = " setup "
            self._fill_rail()
            self._update_chrome()
            self.call_after_refresh(self._focus_panel)

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
            """The last step applies; earlier steps move forward."""
            button = self.query_one("#setup-next", Button)
            last = self._index == len(self._steps) - 1
            button.label = APPLY_LABEL if last else NEXT_LABEL
            button.disabled = last

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
                Static(
                    "Choose where the plan journal lives. Both choices keep the"
                    " database out of version control when it sits in a checkout.",
                    classes="setup-note",
                ),
            ]
            for _key, label, path, note in choices:
                widgets.append(
                    Static(
                        f"[b]{escape_markup(label)}[/] [dim]{escape_markup(str(path))}[/]\n"
                        f"{escape_markup(note)}",
                        classes="setup-choice",
                    )
                )
            widgets.append(Static(f"Current: {draft.placement}", classes="setup-note"))
            return widgets

        def _agents_panel(self) -> list[Any]:
            """Detected hosts with their hint and the skill toggle."""
            draft = self.session.draft
            detected = {host.key: host for host in skills.detect_agents(self.session.home)}
            widgets: list[Any] = [
                Static(
                    "Selected hosts receive the lazyplan skill and managed role"
                    " profiles. Detection is local and read-only.",
                    classes="setup-note",
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
                Static(
                    "Turning skills off leaves the hosts selected but writes no"
                    " skill files, profiles, or model map.",
                    classes="setup-note",
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
                Static(
                    "Hooks record agent sessions, inject the active plan, and check"
                    " commits and stops. Off removes the managed hooks and asks for"
                    " no session tracking.",
                    classes="setup-note",
                ),
                Checkbox(
                    "Add the lazyplan pointer to this checkout's AGENTS.md",
                    value=draft.agents_pointer and pointer_ready,
                    compact=True,
                    id="setup-pointer",
                    disabled=not pointer_ready,
                ),
                Static(
                    "The pointer names the shared database so agents in this"
                    " checkout know where the plans live."
                    if pointer_ready
                    else "The pointer applies only with home placement in a git"
                    " checkout; repo placement sets it up with the repo resources.",
                    classes="setup-note",
                ),
            ]
            return widgets

        def _models_panel(self) -> list[Any]:
            """One tier target per selected host, with catalog options and manual entry."""
            draft = self.session.draft
            widgets: list[Any] = [
                Static(
                    "Each host maps the fast, standard, and deep tiers to one of its"
                    " own models. Type any model id the host accepts, or leave a"
                    " target empty to inherit the host's configured default.",
                    classes="setup-note",
                )
            ]
            for host in draft.agents:
                catalog = self.session.catalogs.get(host)
                label = catalog.label if catalog is not None else host.title()
                widgets.append(Static(f"[b]{escape_markup(label)}[/]", classes="setup-host"))
                if catalog is not None:
                    source = catalog.source or "defaults"
                    widgets.append(
                        Static(
                            f"[dim]source: {escape_markup(source)}[/]",
                            classes="setup-note",
                        )
                    )
                    if catalog.warning:
                        widgets.append(
                            Static(
                                f"[yellow]{escape_markup(catalog.warning)}[/]",
                                classes="setup-note",
                            )
                        )
                for tier in TIERS:
                    current = str((draft.tiers_map.get(tier) or {}).get(host, "") or "").strip()
                    widgets.append(
                        Horizontal(
                            Label(tier, classes="setup-row-label"),
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
                            classes="setup-row",
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
                Static(
                    "Every role names a capability tier and an optional effort"
                    " level. Effort is written only into hosts that have a native"
                    " field; every other host stays at inherit.",
                    classes="setup-note",
                )
            ]
            if not supported:
                widgets.append(
                    Static(
                        "None of the selected hosts has an effort field, so the"
                        " effort selectors are disabled and roles stay at inherit.",
                        classes="setup-note",
                    )
                )
            else:
                widgets.append(
                    Static(
                        f"[dim]effort renders into: {escape_markup(', '.join(supported))}[/]",
                        classes="setup-note",
                    )
                )
            for role in AGENT_ROLES:
                profile = draft.profiles_map.get(role)
                if profile is None:
                    continue
                stored = effort_policy.normalize(profile.effort)
                level = stored if stored in effort_policy.LEVELS else effort_policy.INHERIT
                widgets.append(
                    Horizontal(
                        Label(role, classes="setup-row-label"),
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
                        classes="setup-row",
                    )
                )
                if profile.effort and stored not in effort_policy.LEVELS:
                    widgets.append(
                        Static(
                            f"[yellow]{escape_markup(role)} keeps the stored effort"
                            f" {escape_markup(profile.effort)} until you choose a"
                            " level; choosing inherit clears it.[/]",
                            classes="setup-note",
                        )
                    )
            widgets.append(Button("Reset roles to tier defaults", id="setup-roles-reset"))
            return widgets

        async def _show_step(self) -> None:
            """Swap the panel for the step now selected."""
            panel = self.query_one("#setup-panel", Vertical)
            await panel.remove_children()
            await panel.mount(*self._panel_widgets(self.step))
            self._update_chrome()
            self._highlight_panel_choice()
            self.call_after_refresh(self._focus_panel)

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
                first = _first_focusable(panel)
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
            self._commit_inputs()
            await self._select(self._index - 1)

        async def action_next(self) -> None:
            """Validate this step, then move one step forward."""
            self._commit_inputs()
            self._errors = tuple(self.session.validate())
            if self._errors:
                self._update_chrome()
                return
            await self._select(self._index + 1)

        def action_later(self) -> None:
            """Close without writing anything."""
            self.dismiss(WizardResult())

        def action_cancel(self) -> None:
            """Ask before discarding edits, then close without writing."""
            if not self._dirty():
                self.dismiss(WizardResult())
                return
            from .forms import ConfirmScreen

            def cb(confirmed: bool | None) -> None:
                if confirmed:
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
