"""Full-screen setup wizard: steps, controls, review, and apply.

The screen is a second front end for :class:`SetupSession`; it never writes
outside ``session.apply``. Panels edit the session draft, the rail moves
between steps, and dismissal reports exactly what the app should restart.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from ....infrastructure import skills
from ...setup.layout import resolve_choice
from ...setup.session import SetupSession
from ...setup.state import state_path
from ...setup.steps import WELCOME, Step
from ...shared.design import escape_markup

try:
    from textual import events, on
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.screen import Screen
    from textual.widgets import Button, Label, OptionList, Static
    from textual.widgets.option_list import Option

    from ..navigation import NAV_BINDINGS, NavigationMixin
    from ..query import query_one_opt

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover - stdlib-only interpreter
    _TEXTUAL_OK = False

LATER_LABEL = "Finish later"
NEXT_LABEL = "Next"
APPLY_LABEL = "Apply"


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

        def _panel_widgets(self, step: Step) -> list[Static]:
            """The body of one step; controls replace the summary over time."""
            if step.key == WELCOME.key:
                return [
                    Static(
                        "\n".join(welcome_lines(self.session)),
                        id="setup-welcome",
                        markup=False,
                    )
                ]
            return [
                Static(
                    escape_markup(current_line(self.session, step)),
                    id="setup-current",
                )
            ]

        async def _show_step(self) -> None:
            """Swap the panel for the step now selected."""
            panel = self.query_one("#setup-panel", Vertical)
            await panel.remove_children()
            await panel.mount(*self._panel_widgets(self.step))
            self._update_chrome()
            self.call_after_refresh(self._focus_panel)

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

        async def action_previous(self) -> None:
            """Move one step back; edits stay in the draft."""
            await self._select(self._index - 1)

        async def action_next(self) -> None:
            """Validate this step, then move one step forward."""
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

        @on(Button.Pressed, "#setup-back")
        async def _back(self) -> None:
            await self.action_previous()

        @on(Button.Pressed, "#setup-next")
        async def _next(self) -> None:
            await self.action_next()

        @on(Button.Pressed, "#setup-later")
        def _later(self) -> None:
            self.action_later()
