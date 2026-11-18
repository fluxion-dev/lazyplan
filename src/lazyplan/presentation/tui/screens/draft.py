"""Draft review screen: the document and its annotations in one place."""

from __future__ import annotations

try:
    from textual.app import ComposeResult  # noqa: F401
    from textual.binding import Binding  # noqa: F401
    from textual.containers import Vertical, VerticalScroll  # noqa: F401
    from textual.screen import Screen  # noqa: F401
    from textual.widgets import Static  # noqa: F401

    from ..navigation import NAV_BINDINGS, NavigationMixin
    from ..widgets.taskbar import Taskbar

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover - stdlib-only interpreter
    _TEXTUAL_OK = False

from ....core.ports.app import AppPort
from ....services import drafts as draft_services
from ...shared.design import action_bar

if _TEXTUAL_OK:

    class DraftScreen(NavigationMixin, Screen):
        """Read-only draft document with room for the annotation workspace."""

        navigation_name = "draft"

        BINDINGS = [
            *NAV_BINDINGS,
            Binding("escape", "back", "Back", priority=True),
            Binding("r", "refresh", "Refresh", show=False),
            Binding("U", "update_prompt", "Update", show=False),
        ]

        def __init__(self, store: AppPort, draft_id: int) -> None:
            super().__init__()
            self._store = store
            self.draft_id = draft_id

        def compose(self) -> ComposeResult:
            with Vertical(id="draft-page"):
                yield Static("", id="draft-head", markup=False)
                with VerticalScroll(id="draft-scroll"):
                    yield Static("", id="draft-body", markup=False)
                yield Taskbar("", id="draft-hints")

        def on_mount(self) -> None:
            width = self.app.size.width
            self.set_class(width < 80, "compact")
            self.set_class(width >= 120, "wide")
            self.query_one("#draft-page").border_title = " draft review "
            self.query_one("#draft-scroll").border_title = " document "
            self._reload()
            self.query_one("#draft-scroll", VerticalScroll).focus()

        def _reload(self) -> None:
            """Load the draft and render its blocks and annotations."""
            try:
                detail = draft_services.detail(self._store, self.draft_id)
            except (KeyError, ValueError) as exc:
                self.query_one("#draft-head", Static).update("draft unavailable")
                self.query_one("#draft-body", Static).update(str(exc))
                self.query_one("#draft-hints", Taskbar).set_for_app(
                    action_bar(None, [("esc", "back"), ("r", "retry")])
                )
                return
            draft = detail.draft
            self.query_one("#draft-head", Static).update(
                f"D{draft.id} {draft.title} · {draft.status} · r{draft.revision}"
                f" · {detail.open_annotations}/{detail.total_annotations} open"
            )
            lines: list[str] = []
            for block in detail.blocks:
                indent = "  " * block.level
                lines.append(f"{indent}{block.label} [{block.kind}]")
                lines.extend(f"{indent}  {line}" for line in block.text.splitlines())
                lines.append("")
            lines.append("annotations:")
            if not detail.annotations:
                lines.append("none")
            for row in detail.annotations:
                quote = f' "{row.quote}"' if row.quote else ""
                lines.append(
                    f"A{row.id} [{row.status} {row.kind}] {row.block_key}{quote}"
                    f" ({row.anchor_state}): {row.body}"
                )
                if row.response:
                    lines.append(f"  response: {row.response}")
            self.query_one("#draft-body", Static).update("\n".join(lines))
            self.query_one("#draft-hints", Taskbar).set_for_app(
                action_bar(None, [("esc", "back"), ("r", "refresh")])
            )

        def action_refresh(self) -> None:
            self._reload()

        def action_update_prompt(self) -> None:
            """Open the update screen without leaving this view."""
            self.app.action_update_prompt()  # type: ignore[attr-defined]

        def action_back(self) -> None:
            self.app.pop_screen()
