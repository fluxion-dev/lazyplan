# lazyplan design system

Single source of truth: `src/lazyplan/design.py`. If you add a view,
command, or message, add it there first. Research: `docs/textual-research.md`.
Local skills: `.agents/skills/tui-*`.

## Tokens

Visual: `BORDER = "solid green"`, one-row `#status`. No `Header`,
no `Footer`, no `#activity`, no bottom input. Two-pane `#main`
(`#nav` with focused `FoldTree` + `VerticalScroll#preview`
with `Static#preview-body`) inside `#panel`. Status glyphs
`⬜ todo`, `🔵 doing`, `✅ done`
with ANSI (CLI tty) and Rich (TUI tree) variants. Row grammar
`GLYPH KIND#id title`. Commit chips
and repo pills via `commits_chip` / `repos_chip`.
Empty states from `EMPTY_NO_PLANS` / `EMPTY_FEED` (same in CLI and TUI).

## Widget patterns per surface

- Tree + preview (`tui.py`): `Horizontal#main` with `Vertical#nav`
  (focused `FoldTree`) and `VerticalScroll#preview`
  (`Static#preview-body`). `FoldTree` posts `SelectionChanged` /
  `RowAction` (see `messages.py`, bubbles to App, handled via `@on`);
  `NodeHighlighted` also tracks for compat. `update_preview()` renders
  `store.get_full` without modal. Cursor/fold preserved via
  `call_after_refresh(move_cursor + scroll_to_node)`.
  Reactive `rev` drives local refreshes; `_poll` only handles external
  `fingerprint()` diffs plus `feed` toast. Background upgrade check runs
  in `run_worker`. Native Tree space/shift+space are parked no-ops;
  status and folding live in the modal palette.
- Modal palette (`screens.py` + `tui.py`): `PaletteScreen` (`ModalScreen`,
  `Input#palette-input` + `OptionList#palette-list`) renders
  `PALETTE_SECTIONS` — five labeled groups (Create, Edit, Track, View,
  App) over 18 `PALETTE_COMMANDS` incl. `open-detail` and `toggle-status`.
  Group headers are disabled `Option` rows (8.2.8 has no `Separator`);
  `@on(Changed)` filters commands only, empty sections vanish,
  `Submitted/OptionSelected` dismisses with the command id; App
  `_run_palette_command` dispatches, then focus returns to the tree.
  `c` opens it (`action_command_palette`, screen-stack guarded).
  Every command logs via actor `tui` path.
  `ENABLE_COMMAND_PALETTE = False` keeps the builtin palette from
  stealing keys.
- Filter text: palette command `filter-text` opens `FilterPromptScreen`
  (`_Form` + `Input#filter-input`, `Submitted` applies); the value sets
  `filter_text` and bumps `rev`. `_filtered_tree()` substring-matches
  plan/milestone/task titles, bypasses cap when filtering, shows
  `/query (N plans)` in `#status`. `escape` clears the mode.
- Modals: `_Form` (`ModalScreen`, Esc cancels, `dismiss(None)`); button
  pairs in `.btn-row`; payload dicts on `ok`, `None` on cancel.
  All `on_button_pressed` migrated to `@on(Button.Pressed, "#id")`.
- Detail (`screens.py`): `DetailScreen` focuses `#d-title` on mount,
  `@on(Button.Pressed)` save posts `RowAction("detail-saved")`; App
  refreshes via `_saved`.
- Help: `HELP_TEXT` renders in the `?` overlay, `HelpScreen`, and
  `lpui help` — one string, three surfaces (enforced by tests).

## Keymap

Canonical table in `design.py` as `KEYMAP`; `HELP_TEXT` mirrors it
(enforced by `test_design.py`).

| Key | Action | Surface |
| --- | ------ | ------- |
| j/k, up/down, click | move cursor / select | tree |
| enter, double-click | detail | tree |
| left/right | fold / unfold | tree |
| c | command palette | tree |
| escape | clear filter / cancel | tree, modals |
| esc | cancel | modals |

## Reusable bases

- `_Form(ModalScreen)`: Esc→cancel binding, centered `#dlg` chrome.
- `_row(*buttons) -> Horizontal` (`.btn-row`): every action row in the
  modals.
