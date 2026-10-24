# Textual research notes (pinned 8.2.8)

Reviewed 2026-10-24 against the current guide, widget pages, and changelog.
Textual 8.2.8 remains the latest PyPI release (2026-06-30), so the pin is
current rather than merely frozen.

Distilled from tutorial, guide, widget gallery, how-to, and FAQ at
https://textual.textualize.io/ — links, not copies. Each section ends with
what it means for lazyplan (keyboard-only Tree + modal forms).

## 8.2.x deltas worth knowing

- 8.2.0 added selection over containers and auto-scroll on select
  (`App.ENABLE_SELECT_AUTO_SCROLL`, `SELECT_AUTO_SCROLL_LINES`,
  `SELECT_AUTO_SCROLL_SPEED`). Useful for copying commit/PR text from the
  detail page; don't build a second scroll model around it.
- 8.2.4 added `DOMNode.update_classes(element, add=..., remove=...)` for
  atomic multi-class state changes. Prefer it when a row switches between
  mutually exclusive visual states.
- 8.2.5 added `ansi-dark` / `ansi-light` themes and an `ansi` theme value.
- 8.2.7/8.2.8 improved the Kitty keyboard protocol, including modifier
  detection and alt+backspace on supported terminals. ctrl/alt/cmd bindings
  are safer than before, but still probe with `textual keys` and keep
  letter/arrow fallbacks.
- Current widget constructors add `Footer(compact=...)`,
  `Footer(show_command_palette=...)`, `Input(compact=...)`,
  `Checkbox(compact=...)`, `OptionList(compact=...)`, and
  `SelectionList(compact=...)`. `TextArea` also exposes `soft_wrap`,
  `read_only`, `show_line_numbers`, `theme`, and `highlight_cursor_line`.
- `App.push_screen_wait()` waits for a screen result, but only from a worker;
  lazyplan's callback-based modal flow stays simpler and avoids nested waits.
- `Tree` exposes `reset()`, `clear()`, `select_node()`, `scroll_to_node()`,
  `move_cursor()`, and `set_label()` for programmatic rebuilds without
  reaching into node internals.

## Mental model

- App is the controller: `compose()` yields the static skeleton; runtime
  changes go through `mount()` / `remove()`. `BINDINGS` + `action_*` is the
  primary keyboard API.
- DOM is `App > Screen > widgets`. Messages bubble child → parent → App;
  data flows down via reactives and method calls ("messages up, attributes
  down"). Prefer `@on(Widget.Message, selector)` for forms with many inputs.
- Reactives (`reactive`, `watch_*`, `compute_*`) replace manual refreshes.
- https://textual.textualize.io/tutorial/ · https://textual.textualize.io/guide/events/ · https://textual.textualize.io/guide/reactivity/

lazyplan: tree `NodeHighlighted` drives previews; `enter` pushes the detail dialog;
leaf widgets post `Changed/Submitted/Pressed`, screens coordinate.

## Layout

- `Screen` defaults to vertical stacking. `Vertical`/`Horizontal` are
  `1fr/1fr` with overflow hidden — they never scroll. Scroll needs
  `VerticalScroll` / `HorizontalScroll`, and inner content containers must be
  `height: auto` or the scroller sees no overflow.
- For tight rows use `HorizontalGroup` / `VerticalGroup` (auto cross-size).
- `dock: top|bottom` + fixed heights for chrome; `1fr` shares the remainder.
- `align` goes on the parent; `display: none` removes layout,
  `visibility: hidden` keeps space.
- https://textual.textualize.io/guide/layout/ · https://textual.textualize.io/how-to/work-with-containers/ · https://textual.textualize.io/how-to/design-a-layout/

lazyplan: `#cards { height: auto; }` inside `VerticalScroll` is what makes the
editor-area scroll; button rows are `Horizontal` with compact CSS.

## Styling

- App CSS (`App.CSS`) always beats widget `DEFAULT_CSS` (scoped, lower
  specificity). Selectors: `Type` (matches subclasses), `#id` (immutable),
  `.class` (mutable), pseudo-classes `:focus`, `:focus-within`, `:disabled`.
- Prefer state classes (`add_class` / `set_class`) over inline `styles.*`.
- Component classes style sub-parts: `tree--cursor`, `input--cursor`,
  `text-area--gutter`, `toggle--button`. Theme vars `$primary`, `$panel`,
  `$foreground`, `$success`, `$error`.
- https://textual.textualize.io/guide/CSS/ · https://textual.textualize.io/guide/styles/ · https://textual.textualize.io/guide/design/

lazyplan: all row grammar and tokens live in `design.py` (`APP_CSS`); app CSS
wins over widget defaults — scope dialog rules under `#dlg`.

## Widgets in use

- **Tree** (`widgets/tree/`): `TreeNode.data` carries model ids;
  `NodeHighlighted` (cursor) vs `NodeSelected` (enter); `space` toggles,
  `shift+space` expands all — never rebind these globally. `scroll_to_node`,
  `move_cursor`, `set_label` for programmatic control.
- **Input** (`widgets/input/`): single-line, `Changed/Submitted/Blurred`,
  validators + `validate_on`, `restrict`, `compact=True` safe on 8.2.8.
  Consumes most keys when focused — global keys need `priority=True`.
- **TextArea** (`widgets/text_area/`): `text` reactive, default
  `tab_behavior="focus"` (Tab leaves); `"indent"` traps Tab and releases on
  Esc. Mounting many TextAreas is heavy — prefer one-line Inputs with
  focus-expand. Theme parts (`text-area--gutter`) need theme context.
- **Checkbox** (`widgets/checkbox/`): `value` reactive, initial value does
  not emit; `enter/space` toggles; `compact=True` safe.
- **Button** (`widgets/button/`): `Pressed` message (or `action=` instead);
  spacing comes from `min-width:16`, not padding — shrink via CSS.
  `compact` (3.2.0+) and `flat` (6.1.0+) safe on 8.2.8.
- **Collapsible** (`widgets/collapsible/`): constructor children collapse;
  post-mounts land outside the body — prebuild all children. `collapsed`
  reactive, `Toggled/Expanded/Collapsed` messages, `enter` toggles title.
- **Header/Footer** (`widgets/header/`, `widgets/footer/`): `Footer`
  auto-shows active bindings; `show=False` hides; per-screen titles via
  `Screen.TITLE`.
- **Screen/ModalScreen** (`guide/screens/`, `api/screen/`): stack via
  `push_screen` / `pop_screen` / `switch_screen`; `dismiss(result)` returns
  data; only the top screen receives input. lazyplan uses `ModalScreen`
  dialogs only — the fullscreen editor is gone, `DetailScreen` edits in
  place.

## Keys, focus, modality

- Binding lookup: focused widget → up DOM → App; `priority=True` checked
  first (saves/quits that must work inside inputs). `Footer` shows them.
- Never mutate `BINDINGS` at runtime — use `check_action()` + 
  `refresh_bindings()` or `reactive(..., bindings=True)`.
- Terminals swallow many combos; stick to letters, F-keys, space, arrows,
  ctrl/shift; probe with `textual keys`. `Input` already binds ~20 keys.
- Focus: `can_focus`, `widget.focus()`, Tab order automatic,
  `Focus/Blur` + bubbling `DescendantFocus/DescendantBlur`.
- https://textual.textualize.io/guide/input/ · https://textual.textualize.io/guide/actions/ · https://textual.textualize.io/FAQ/

lazyplan: modal-owns-key guards (`len(screen_stack) > 1`), select-first
notifies, snapshot-based dirty check (mount-time `Changed` storm).

## Mount / rebuild / scroll discipline

- `await container.mount(w)` then `call_after_refresh` before any
  `scroll_to_widget` — scrolling pre-layout is a silent no-op.
- `await box.remove_children()` before remounting same ids (`DuplicateIds`
  otherwise). Rebuilds drop focus/scroll — re-focus and re-scroll.
- https://textual.textualize.io/how-to/render-and-compose/ · https://textual.textualize.io/guide/input/#bindings

lazyplan: `_rebuild` awaits removal and mounts; anchor scroll runs via
`call_after_refresh`.

## Testing

- `async with app.run_test(size=(w,h)) as pilot:` headless;
  `press/click/hover/pause`; assert on state, not visuals. Clicks on covered
  or out-of-view widgets fail by design. Snapshot plugin
  `pytest-textual-snapshot` for SVG regression.
- https://textual.textualize.io/guide/testing/ · https://textual.textualize.io/api/pilot/

lazyplan: pilot patterns in `tests/test_screens_esc.py`; state asserts on
`Store` reads; explicit viewport sizes per test.

## Overhaul learnings (P52 master-detail)

- Events guide applied: message queue guarantees ordering; base-class
  handlers run unless `prevent_default()`; `bubble=True` custom messages
  (`SelectionChanged`, `RowAction` in `src/lazyplan/messages.py`) flow
  child -> parent -> App with data messages-up. `@on(..., selector)`
  replaces generic `on_button_pressed`; `DescendantFocus/Blur` via `@on`
  for expand/collapse. Async handlers + `run_worker(thread=True)` for
  upgrade check; `call_from_thread` for toasts.
  https://textual.textualize.io/guide/events/
- Reactivity replaces polling: local writes bump `rev: reactive(0)`,
  `watch_rev` refreshes; `_poll` stays only for external `fingerprint()`
  diffs. `status_filter`/`filter_text` feed `_filtered_tree()`; preview
  watches selection via `update_preview()`.
  https://textual.textualize.io/guide/reactivity/
- Layout: `Screen` vertical by default; `Horizontal#main` splits nav/preview
  `1fr/1fr` above 100 columns. `_on_resize` toggles `#main.narrow`, which
  hides the preview; `VerticalScroll` needs inner `height: auto`; `dock`
  chrome, `display: none` removes layout. Focus restore via
  `call_after_refresh` after rebuild, else cursor is `None`.
  https://textual.textualize.io/guide/layout/
- Progressive disclosure: plans start collapsed; `_expanded` holds the
  explicit open keys, and `_refreshing` suppresses Tree expand/collapse
  events during a rebuild. Right/`z` reveals milestones, then tasks.
  Done plans are dimmed and sorted last.
  https://textual.textualize.io/guide/reactivity/
- Palette/discovery: built-in `CommandPalette` stays disabled
  (`ENABLE_COMMAND_PALETTE = False`) so no hidden second palette owns a
  key. The centered `PaletteScreen` modal renders `commands.py` sections
  (Create/Edit/View/App) with live `@on(Changed)` filtering, a match
  count, a no-match row, and context-disabled options that name the
  reason. The list scrolls inside a max-height `#dlg`, so every command is
  reachable at 80x24. `Submitted/OptionSelected` dismisses with the id and
  `_run_palette_command` dispatches through registry handlers. Headers are
  disabled `Option` rows (no `Separator` in 8.2.8). `?` opens the
  task-grouped help; `/` opens the filter prompt. Native Tree
  space/shift+space are parked as no-ops in `FoldTree`.
- Detail: a plain `Screen` with read and edit modes. Read mode is a
  scrolling `Static` card; `e` swaps to labeled inputs with a dirty
  snapshot, `ctrl+s` saves, and `Esc` confirms before discarding.
  https://textual.textualize.io/guide/screens/
- UX references: lazygit left-tree/right-detail ratio, k9s `describe`
  pane, VSCode `ctrl+p`/`ctrl+k` palette, Linear side-peek
  for detail, posting modal validation. Master-detail + progressive
  disclosure beats single-tree modals for 300-task DBs.
