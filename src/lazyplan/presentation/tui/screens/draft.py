"""Draft review screen: selectable document blocks and anchored feedback."""

from __future__ import annotations

try:
    from textual.app import ComposeResult  # noqa: F401
    from textual.binding import Binding  # noqa: F401
    from textual.containers import Vertical, VerticalScroll  # noqa: F401
    from textual.geometry import Offset  # noqa: F401
    from textual.screen import Screen  # noqa: F401
    from textual.selection import Selection  # noqa: F401
    from textual.widgets import Static  # noqa: F401

    from ..navigation import NAV_BINDINGS, NavigationMixin
    from ..widgets.draft_document import DraftBlockBody, DraftBlockView
    from ..widgets.taskbar import Taskbar

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover - stdlib-only interpreter
    _TEXTUAL_OK = False

from ....core.ports.app import AppPort
from ....services import drafts as draft_services
from ....services.draft_content import DraftAnchor, DraftBlock
from ...shared.design import action_bar


def _line_start(text: str, line: int) -> int:
    """Absolute offset where one split-lines line begins."""
    return sum(len(row) for row in text.splitlines(keepends=True)[:line])


def _selection_offsets(text: str, selection: Selection) -> tuple[int, int]:
    """Absolute start/end offsets for one text selection."""
    lines = text.splitlines(keepends=True)
    if not lines:
        return 0, 0

    def absolute(offset: Offset) -> int:
        line = min(max(offset.y, 0), len(lines) - 1)
        column = min(max(offset.x, 0), len(lines[line].rstrip("\r\n")))
        return _line_start(text, line) + column

    start = Offset(0, 0) if selection.start is None else selection.start
    end = selection.end or Offset(len(lines) - 1, len(lines[-1].rstrip("\r\n")))
    return absolute(start), absolute(end)


def anchor_from_selection(block: DraftBlock, selection: Selection) -> DraftAnchor:
    """Turn one Textual selection into a block anchor with exact offsets."""
    quote = selection.extract(block.text)
    if not quote:
        return DraftAnchor(block.key)
    start, end = _selection_offsets(block.text, selection)
    return DraftAnchor(block.key, quote, start, end)


if _TEXTUAL_OK:

    class DraftScreen(NavigationMixin, Screen):
        """Read-only draft document with selectable blocks for annotation."""

        navigation_name = "draft"

        BINDINGS = [
            *NAV_BINDINGS,
            Binding("escape", "back", "Back", priority=True),
            Binding("j", "next_block", "Next block", show=False),
            Binding("k", "prev_block", "Prev block", show=False),
            Binding("a", "annotate", "Annotate"),
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
                    with Vertical(id="draft-body"):
                        yield Static("", id="draft-empty", markup=False)
                yield Taskbar("", id="draft-hints")

        def on_mount(self) -> None:
            width = self.app.size.width
            self.set_class(width < 80, "compact")
            self.set_class(width >= 120, "wide")
            self.query_one("#draft-page").border_title = " draft review "
            self.query_one("#draft-scroll").border_title = " document "
            self._reload()

        def _reload(self) -> None:
            """Load the draft and mount one view per block."""
            body = self.query_one("#draft-body", Vertical)
            body.remove_children()
            try:
                detail = draft_services.detail(self._store, self.draft_id)
            except (KeyError, ValueError) as exc:
                self.query_one("#draft-head", Static).update("draft unavailable")
                body.mount(Static(str(exc), markup=False, classes="draft-block-body"))
                self.query_one("#draft-hints", Taskbar).set_for_app(
                    action_bar(None, [("esc", "back"), ("r", "retry")])
                )
                return
            draft = detail.draft
            self.query_one("#draft-head", Static).update(
                f"D{draft.id} {draft.title} · {draft.status} · r{draft.revision}"
                f" · {detail.open_annotations}/{detail.total_annotations} open"
            )
            body.mount_all([DraftBlockView(block) for block in detail.blocks])
            self.query_one("#draft-hints", Taskbar).set_for_app(
                action_bar(None, [("j/k", "block"), ("a", "annotate"), ("esc", "back")])
            )
            self.call_after_refresh(self._focus_first)

        def _focused_body(self) -> DraftBlockBody | None:
            focused = self.focused
            return focused if isinstance(focused, DraftBlockBody) else None

        def _selected_bodies(self) -> list[tuple[DraftBlockBody, Selection]]:
            return [
                (widget, selection)
                for widget, selection in self.selections.items()
                if isinstance(widget, DraftBlockBody)
            ]

        def current_anchor(self) -> DraftAnchor | None:
            """The selected quote, else the focused block, else nothing."""
            selected = self._selected_bodies()
            if len(selected) > 1:
                self.notify("select text within one draft block", timeout=4)
                return None
            if selected:
                body, selection = selected[0]
                return anchor_from_selection(body.block, selection)
            focused = self._focused_body()
            if focused is not None:
                return DraftAnchor(focused.block.key)
            return None

        def _bodies(self) -> list[DraftBlockBody]:
            return list(self.query(DraftBlockBody))

        def _focus_first(self) -> None:
            bodies = self._bodies()
            if bodies:
                bodies[0].focus()

        def action_next_block(self) -> None:
            bodies = self._bodies()
            if not bodies:
                return
            focused = self.focused
            index = bodies.index(focused) if focused in bodies else -1
            bodies[min(index + 1, len(bodies) - 1)].focus()

        def action_prev_block(self) -> None:
            bodies = self._bodies()
            if not bodies:
                return
            focused = self.focused
            index = bodies.index(focused) if focused in bodies else len(bodies)
            bodies[max(index - 1, 0)].focus()

        def action_annotate(self) -> None:
            """Open the annotation form for the current selection or block."""
            anchor = self.current_anchor()
            if anchor is None:
                self.notify("select a block or some text first", timeout=4)
                return
            self.notify(f"annotate {anchor.block_key}: anchor captured", timeout=4)

        def action_refresh(self) -> None:
            self._reload()

        def action_update_prompt(self) -> None:
            """Open the update screen without leaving this view."""
            self.app.action_update_prompt()  # type: ignore[attr-defined]

        def action_back(self) -> None:
            self.app.pop_screen()
