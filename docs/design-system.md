# lazyplan design system

Single source of truth: `src/lazyplan/design.py`. If you add a view,
command, or message, add it there first. Research: `docs/textual-research.md`.
Local skills: `.agents/skills/tui-*`.

## Tokens

Visual: `BORDER = "solid green"`, `PANEL_HEIGHT = "1fr"`, one-row
`#activity` / `#statusbar`, `#filter` height 1. Two-pane `#main`
(`#nav` + `#preview`, each `1fr`, min 30) inside `#panel`. Status glyphs
`⬜ todo`, `🔵 doing`, `✅ done`
with ANSI (CLI tty) and Rich (TUI tree) variants. Row grammar
`GLYPH KIND#id title`; priority is model-only, never rendered. Commit chips
and repo pills via `commits_chip` / `repos_chip`.
Empty states from `EMPTY_NO_PLANS` / `EMPTY_FEED` (same in CLI and TUI).

## Widget patterns per surface

- Tree + preview (`tui.py`): `Horizontal#main` with `Vertical#nav`
  (`Input#filter` + focused `FoldTree`) and `VerticalScroll#preview`
  (`Static#preview-body`). `FoldTree` posts `SelectionChanged` /
  `RowAction` (see `messages.py`, bubbles to App, handled via `@on`);
  `NodeHighlighted` also tracks for compat. `update_preview()` renders
  `store.get_full` without modal. Cursor/fold preserved via
  `call_after_refresh(move_cursor + scroll_to_node)`.
  Reactive `rev` drives local refreshes; `_poll` only handles external
  `fingerprint()` diffs plus `feed` toast. Background upgrade check runs
  in `run_worker`.
- Filter (`tui.py`): `Input#filter` (`/` focuses, `esc` clears),
  `@on(Input.Changed)` sets `filter_text` and bumps `rev`;
  `_filtered_tree()` substring-matches plan/milestone/task titles,
  bypasses cap when filtering, shows `/query (N plans)` in statusbar.
- Palette (`screens.py`): `PaletteScreen` (`ModalScreen`, `Input#palette-input`
  + `OptionList#palette-list`), `@on(Changed/Submitted/OptionSelected)`,
  substring filter, `dismiss(cmd)`; App `action_palette` dispatches
  (`ctrl+p`, `ENABLE_COMMAND_PALETTE = False` to own the key).
  Every command logs via actor `tui` path.
- Editor (`screens.py`): `ProjectEditorScreen` — `VerticalScroll#editor`
  with `height: auto` `#cards`; one `Collapsible` per entity (constructor
  children only), collapsed except the focus chain; single-line `Input`s,
  descriptions focus-expand via `@on(DescendantFocus/Blur)`; actions on
  `.btn-row` (`Horizontal`, `height: auto`) with short labels; snapshot
  dirty check; `priority=True` on `esc`/`ctrl+s`; saves post
  `RowAction("editor-saved")`.
- Modals: `_Form` (`ModalScreen`, Esc cancels, `dismiss(None)`); button
  pairs in `.btn-row`; payload dicts on `ok`, `None` on cancel.
  All `on_button_pressed` migrated to `@on(Button.Pressed, "#id")`
  with card dispatcher on `.btn-row Button`.
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
| space | cycle status | tree |
| n / P / M / T | new context / plan / milestone / task | tree |
| e | project editor | tree |
| X | export plan .md | tree |
| c | tick criteria | tree |
| d | delete (confirm) | tree |
| z/Z, left/right | fold | tree |
| f | status filter | tree |
| A | show all / capped | tree |
| ctrl+p | command palette | tree |
| slash, escape | search filter / clear | tree |
| r | refresh | tree |
| ? | help | tree |
| q | quit | tree |
| ctrl+s | save all | editor |
| esc | close (dirty prompts) / cancel | editor, modals |

## Reusable bases

- `_Form(ModalScreen)`: Esc→cancel binding, centered `#dlg` chrome.
- `_row(*buttons) -> Horizontal` (`.btn-row`): every action row in the
  editor and modals.
- `ProjectEditorScreen`: anchor focus + scroll, snapshot dirty, per-row
  and Save-all writes with `actor="tui"`, `ValueError → notify`.
