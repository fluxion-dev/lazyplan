"""Modal health screen: what is missing, what it costs, and how to fix it."""

from __future__ import annotations

try:
    from textual import on
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical, VerticalScroll
    from textual.screen import ModalScreen
    from textual.widgets import Button, Label, Static

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover
    _TEXTUAL_OK = False

from ...setup.health import ERROR, HealthFinding
from ...shared.design import escape_markup
from ..navigation import NAV_BINDINGS, NavigationMixin

LATER = "later"
NEVER = "never"
INSTALL = "install"
INSTALL_NOTE = "Install & restart adds the missing skills and hooks, then restarts lpui."


def _finding_lines(finding: HealthFinding) -> list[str]:
    mark = "[red]✗[/]" if finding.severity == ERROR else "[yellow]![/]"
    hidden = {"never": " [dim](never ask)[/]", "deferred": " [dim](not now)[/]"}
    tag = hidden.get(finding.decision, "")
    lines = [f"{mark} [b]{escape_markup(finding.label)}[/]{tag}"]
    lines.append(f"  {escape_markup(finding.capability)}")
    if finding.fix:
        lines.append(f"  [dim]fix:[/] {escape_markup(finding.fix)}")
    return lines


def health_body(findings: tuple[HealthFinding, ...]) -> str:
    """Intro, one block per finding, then what Install & restart does."""
    lines = [
        "Some of what lazyplan relies on is missing. Until it's fixed, lazyplan can do less:",
        "",
    ]
    for finding in findings:
        lines.extend(_finding_lines(finding))
        lines.append("")
    if any(finding.fixable for finding in findings):
        lines.append(INSTALL_NOTE)
    return "\n".join(lines).rstrip()


if _TEXTUAL_OK:

    class HealthScreen(NavigationMixin, ModalScreen[str | None]):
        """List findings; dismiss with the chosen action.

        On startup it offers Not now and Never ask for the open findings. In
        review it lists every finding, hidden ones included, and only closes.
        """

        navigation_name = "health"

        BINDINGS = [*NAV_BINDINGS, Binding("escape", "cancel", "Not now", priority=True)]

        def __init__(self, findings: tuple[HealthFinding, ...], review: bool = False) -> None:
            super().__init__()
            self.findings = findings
            self.review = review

        def on_mount(self) -> None:
            self.query_one("#dlg").border_title = "HEALTH CHECK"

        def compose(self) -> ComposeResult:
            with Vertical(id="dlg"):
                yield Label("lazyplan health check")
                with VerticalScroll(id="health-scroll"):
                    yield Static(health_body(self.findings), id="health-body")
                fixable = any(finding.fixable for finding in self.findings)
                with Horizontal(classes="btn-row"):
                    if fixable:
                        yield Button("Install & restart", id="health-install", variant="primary")
                    yield Button(
                        "Close" if self.review else "Not now",
                        id="health-later",
                        variant="default" if fixable else "primary",
                    )
                    if not self.review:
                        yield Button("Never ask", id="health-never")

        @on(Button.Pressed, "#health-install")
        def _install(self) -> None:
            self.dismiss(INSTALL)

        @on(Button.Pressed, "#health-never")
        def _never(self) -> None:
            self.dismiss(NEVER)

        @on(Button.Pressed, "#health-later")
        def _later(self) -> None:
            self.action_cancel()

        def action_cancel(self) -> None:
            self.dismiss(None if self.review else LATER)
