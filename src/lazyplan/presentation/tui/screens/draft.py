"""Draft review screen: selectable blocks, annotations, and promotion."""

from __future__ import annotations

try:
    from textual import on
    from textual.app import ComposeResult  # noqa: F401
    from textual.binding import Binding  # noqa: F401
    from textual.containers import Horizontal, Vertical, VerticalScroll  # noqa: F401
    from textual.screen import Screen  # noqa: F401
    from textual.selection import Selection  # noqa: F401
    from textual.widgets import OptionList, Static  # noqa: F401
    from textual.widgets.option_list import Option  # noqa: F401

    from ..navigation import NAV_BINDINGS, NavigationMixin
    from ..views.draft import anchor_from_selection
    from ..widgets.draft_document import DraftBlockBody, DraftBlockView
    from ..widgets.taskbar import Taskbar
    from .draft_forms import AnnotationForm
    from .forms import ConfirmScreen, FilterPromptScreen
    from .help import TextScreen

    _TEXTUAL_OK = True
except ImportError:  # pragma: no cover - stdlib-only interpreter
    _TEXTUAL_OK = False

from ....core.entities import DraftAnnotation
from ....core.kinds import DRAFT_FORMAT_DOCUMENT
from ....core.ports.app import AppPort
from ....services import drafts as draft_services
from ....services.draft_content import DraftAnchor
from ....services.drafts import DraftDetail
from ...shared.design import action_bar

if _TEXTUAL_OK:

    class DraftScreen(NavigationMixin, Screen):
        """Draft document on the left, annotations on the right."""

        navigation_name = "draft"

        BINDINGS = [
            *NAV_BINDINGS,
            Binding("escape", "back", "Back", priority=True),
            Binding("j", "next_block", "Next block", show=False),
            Binding("k", "prev_block", "Prev block", show=False),
            Binding("a", "annotate", "Annotate"),
            Binding("P", "promote", "Promote"),
            Binding("x", "dismiss_annotation", "Dismiss"),
            Binding("d", "delete_annotation", "Delete"),
            Binding("r", "refresh", "Refresh", show=False),
            Binding("U", "update_prompt", "Update", show=False),
        ]

        def __init__(self, store: AppPort, draft_id: int) -> None:
            super().__init__()
            self._store = store
            self.draft_id = draft_id
            self._detail: DraftDetail | None = None

        def compose(self) -> ComposeResult:
            with Vertical(id="draft-page"):
                yield Static("", id="draft-head", markup=False)
                with Horizontal(id="draft-main"):
                    with VerticalScroll(id="draft-scroll"):
                        with Vertical(id="draft-body"):
                            yield Static("", id="draft-empty", markup=False)
                    with Vertical(id="draft-side"):
                        yield Static("annotations", id="draft-side-title", markup=False)
                        yield OptionList(id="draft-annotations")
                        yield Static("", id="draft-annotation-detail", markup=False)
                yield Taskbar("", id="draft-hints")

        def on_mount(self) -> None:
            width = self.app.size.width
            self.set_class(width < 80, "compact")
            self.set_class(width >= 120, "wide")
            self.query_one("#draft-page").border_title = " draft review "
            self.query_one("#draft-scroll").border_title = " document "
            self.query_one("#draft-side").border_title = " feedback "
            self._reload()

        def _reload(self) -> None:
            """Load the draft, mount its blocks, and refresh the sidebar."""
            body = self.query_one("#draft-body", Vertical)
            body.remove_children()
            try:
                detail = draft_services.detail(self._store, self.draft_id)
            except (KeyError, ValueError) as exc:
                self._detail = None
                self.query_one("#draft-head", Static).update("draft unavailable")
                body.mount(Static(str(exc), markup=False, classes="draft-block-body"))
                self.query_one("#draft-annotations", OptionList).clear_options()
                self.query_one("#draft-annotation-detail", Static).update("")
                self.query_one("#draft-hints", Taskbar).set_for_app(
                    action_bar(None, [("esc", "back"), ("r", "retry")])
                )
                return
            self._detail = detail
            draft = detail.draft
            self.query_one("#draft-head", Static).update(
                f"D{draft.id} {draft.title} · {draft.status} · r{draft.revision}"
                f" · {draft.format}"
                f" · {detail.open_annotations}/{detail.total_annotations} open"
            )
            body.mount_all([DraftBlockView(block) for block in detail.blocks])
            self._load_annotations()
            self.query_one("#draft-hints", Taskbar).set_for_app(
                action_bar(
                    None,
                    [
                        ("j/k", "block"),
                        ("a", "annotate"),
                        ("P", "promote"),
                        ("esc", "back"),
                    ],
                )
            )
            self.call_after_refresh(self._focus_first)

        def _load_annotations(self) -> None:
            """Fill the sidebar, preserving the highlighted annotation."""
            options = self.query_one("#draft-annotations", OptionList)
            selected = self._selected_annotation_id()
            options.clear_options()
            if self._detail is None:
                self._show_annotation_detail()
                return
            for row in self._detail.annotations:
                label = f"A{row.id} [{row.status} {row.kind}] {row.block_key} · {row.body[:44]}"
                options.add_option(Option(label, id=str(row.id)))
            if not self._detail.annotations:
                options.add_option(Option("No annotations yet", id="none", disabled=True))
                self._show_annotation_detail()
                return
            index = 0
            for position, row in enumerate(self._detail.annotations):
                if row.id == selected:
                    index = position
                    break
            options.highlighted = index
            self._show_annotation_detail()

        def _selected_annotation_id(self) -> int | None:
            if self._detail is None:
                return None
            options = self.query_one("#draft-annotations", OptionList)
            highlighted = options.highlighted
            if highlighted is None or highlighted >= len(self._detail.annotations):
                return None
            return self._detail.annotations[highlighted].id

        def _selected_annotation(self) -> DraftAnnotation | None:
            if self._detail is None:
                return None
            options = self.query_one("#draft-annotations", OptionList)
            highlighted = options.highlighted
            if highlighted is None or highlighted >= len(self._detail.annotations):
                return None
            return self._detail.annotations[highlighted]

        def _focused_annotation(self) -> DraftAnnotation | None:
            options = self.query_one("#draft-annotations", OptionList)
            if self.focused is not options:
                return None
            return self._selected_annotation()

        def _show_annotation_detail(self) -> None:
            target = self.query_one("#draft-annotation-detail", Static)
            row = self._selected_annotation()
            if row is None:
                target.update("No annotations yet.\nSelect text or a block and press a.")
                return
            lines = [
                f"A{row.id} {row.kind} · {row.status} · {row.author} · anchor {row.anchor_state}",
                f"block: {row.block_key}",
            ]
            if row.quote:
                lines.append(f'quote: "{row.quote}"')
            lines.append(f"body: {row.body}")
            if row.response:
                lines.append(f"response: {row.response}")
            target.update("\n".join(lines))

        def _block_label(self, block_key: str) -> str:
            if self._detail is None:
                return block_key
            for block in self._detail.blocks:
                if block.key == block_key:
                    return block.label
            return block_key

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
            label = self._block_label(anchor.block_key)
            self.app.push_screen(
                AnnotationForm(anchor, label),
                lambda data: self._save_annotation(anchor, data),
            )

        def _save_annotation(self, anchor: DraftAnchor, data: dict | None) -> None:
            if not data:
                return
            try:
                draft_services.annotate(
                    self._store,
                    self.draft_id,
                    anchor.block_key,
                    str(data.get("kind") or "comment"),
                    str(data.get("body") or ""),
                    quote=anchor.quote,
                    start_offset=anchor.start_offset,
                    end_offset=anchor.end_offset,
                    author="tui",
                )
            except (KeyError, ValueError) as exc:
                self.notify(f"error: {exc}", timeout=5)
                return
            self.notify("annotation sent to the agent", timeout=4)
            self.clear_selection()
            self._reload()

        @on(OptionList.OptionHighlighted, "#draft-annotations")
        def _highlight_annotation(self, event: OptionList.OptionHighlighted) -> None:
            self._show_annotation_detail()

        @on(OptionList.OptionSelected, "#draft-annotations")
        def _open_annotation(self, event: OptionList.OptionSelected) -> None:
            self.action_view_annotation()
            event.stop()

        def action_view_annotation(self) -> None:
            row = self._focused_annotation()
            if row is None:
                self.notify("focus the annotation list first", timeout=4)
                return
            lines = [
                f"A{row.id} {row.kind} · {row.status} · {row.author} · anchor {row.anchor_state}",
                f"block: {row.block_key}",
            ]
            if row.quote:
                lines.append(f'quote: "{row.quote}"')
            lines.append(f"body: {row.body}")
            if row.response:
                lines.append(f"response: {row.response}")
            self.app.push_screen(TextScreen(f"A{row.id} {row.kind}", "\n".join(lines)))

        def action_promote(self) -> None:
            """Create the plan tree from a clean draft."""
            if self._detail is None:
                return
            draft = self._detail.draft
            if draft.status == "promoted":
                self.notify("this draft is already promoted", timeout=4)
                return
            if draft.status != "review":
                self.notify("the agent must revise this draft before promotion", timeout=5)
                return
            if draft.format != DRAFT_FORMAT_DOCUMENT:
                self.notify("this draft is a sketch; formalize it before promoting", timeout=5)
                return
            if self._detail.open_annotations:
                self.notify("resolve or dismiss open annotations first", timeout=5)
                return

            def cb(confirmed: bool | None) -> None:
                if not confirmed:
                    return
                try:
                    promotion = draft_services.promote(self._store, self.draft_id, actor="tui")
                except (KeyError, ValueError) as exc:
                    self.notify(f"error: {exc}", timeout=5)
                    return
                self.notify(
                    f"created P{promotion.plan.id} {promotion.plan.name!r}",
                    timeout=8,
                )
                self.app.select_row("plan", promotion.plan.id)  # type: ignore[attr-defined]

            self.app.push_screen(
                ConfirmScreen(
                    f"Promote D{self.draft_id} into the plan queue?",
                    confirm_label="Promote",
                    variant="primary",
                ),
                cb,
            )

        def action_dismiss_annotation(self) -> None:
            row = self._focused_annotation()
            if row is None:
                self.notify("focus the annotation list first", timeout=4)
                return

            def cb(reason: str | None) -> None:
                if reason is None:
                    return
                if not reason.strip():
                    self.notify("a dismissal needs a reason", timeout=3)
                    return
                try:
                    draft_services.dismiss(self._store, row.id, reason.strip(), actor="tui")
                except (KeyError, ValueError) as exc:
                    self.notify(f"error: {exc}", timeout=5)
                    return
                self._reload()

            self.app.push_screen(
                FilterPromptScreen(
                    title=f"Dismiss A{row.id}? Why?",
                    placeholder="reason for dismissing…",
                    submit_label="Dismiss",
                ),
                cb,
            )

        def action_delete_annotation(self) -> None:
            row = self._focused_annotation()
            if row is None:
                self.notify("focus the annotation list first", timeout=4)
                return
            if row.status != "open":
                self.notify("only open annotations can be deleted", timeout=4)
                return

            def cb(confirmed: bool | None) -> None:
                if not confirmed:
                    return
                try:
                    draft_services.delete_annotation(self._store, row.id, actor="tui")
                except (KeyError, ValueError) as exc:
                    self.notify(f"error: {exc}", timeout=5)
                    return
                self._reload()

            self.app.push_screen(ConfirmScreen(f"Delete A{row.id}?"), cb)

        def action_refresh(self) -> None:
            self._reload()

        def action_update_prompt(self) -> None:
            """Open the update screen without leaving this view."""
            self.app.action_update_prompt()  # type: ignore[attr-defined]

        def action_back(self) -> None:
            self.app.pop_screen()
