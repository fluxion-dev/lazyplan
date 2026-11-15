"""Full-screen setup wizard shell: steps, navigation, review, and apply.

The screen is a second front end for :class:`SetupSession`; it never writes
outside ``session.apply``. Panels edit the session draft, the rail moves
between steps, and dismissal reports exactly what the app should restart.
"""

from __future__ import annotations

import copy
import io
from typing import Any

from ....core.policies import effort as effort_policy
from ....core.policies.agents import DEFAULT_ROLE_TIERS, HOSTS
from ....core.policies.hooks import MODES
from ...setup.health import HealthFinding
from ...setup.session import SetupSession, SetupSessionError
from ...setup.steps import APPEARANCE, Step
from ...setup.triggers import WizardNeed
from ...shared.design import escape_markup
from .setup_panels import SetupPanelsScreen
from .setup_support import (
    APPLY_LABEL,
    INHERIT,
    LATER_LABEL,
    NEXT_LABEL,
    Checks,
    WizardResult,
    hint_text,
    review_sections,
)

__all__ = [
    "INHERIT",
    "SetupWizardScreen",
    "WizardResult",
    "review_sections",
]

try:
    from textual import events, on
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical, VerticalScroll
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

    from ..navigation import NAV_BINDINGS
    from ..query import query_one_opt
    from ..theme.themes import THEME_NAMES
    from ..widgets.setup_controls import first_focusable

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover - stdlib-only interpreter
    _TEXTUAL_OK = False


if _TEXTUAL_OK:

    class SetupWizardScreen(SetupPanelsScreen):
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
            start: str | WizardNeed = "",
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
            self._result: WizardResult | None = None

        def _start_index(self, start: str | WizardNeed) -> int:
            """The requested step when it is visible, else the first one.

            The startup controller hands over the :class:`WizardNeed` that
            opened the wizard. The reason explains why the wizard is due; the
            run still starts at Welcome so the user reads the whole contract.
            """
            key = "" if isinstance(start, WizardNeed) else start
            keys = [step.key for step in self._steps]
            if key in keys:
                return keys.index(key)
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
            if self.step.key == APPEARANCE.key:
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
            if self.step.key == APPEARANCE.key:
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
