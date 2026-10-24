---
name: tui-widgets
description: Widget catalog for the lazyplan TUI — which widget to use for what, with pinned-version flags. Use when adding or changing any Tree, Input, TextArea, Checkbox, Button, Collapsible, Header, Footer, Screen, or modal in src/lazyplan/tui.py or screens.py.
license: MIT
compatibility: opencode, claude-code, codex, gemini-cli, cursor
---
# tui-widgets — widget catalog (Textual 8.2.8 pinned)

Reviewed 2026-10-24 against the current widget gallery and per-widget pages.
8.2.8 is the latest PyPI release.

Distilled from https://textual.textualize.io/widget_gallery/ plus
`docs/textual-research.md`. Rules first, links second.

## Choices

- Hierarchy display: `Tree` with model ids in `TreeNode.data`.
  `NodeHighlighted` drives previews, `NodeSelected` (enter) opens editors.
  Never rebind `space` (toggle), `shift+space` (expand all), or arrows.
  Programmatic control: `reset()`, `clear()`, `select_node()`,
  `scroll_to_node()`, `move_cursor()`, `set_label()`.
- Single-line entry: `Input`. Multi-line: `TextArea` — but mounting many
  TextAreas is heavy, so lists use one-line Inputs with focus-expand.
  `TextArea` also takes `soft_wrap`, `read_only`, `show_line_numbers`,
  `theme`, and `highlight_cursor_line`.
- Toggles: `Checkbox` (`enter`/`space` toggles, initial value is silent).
- Actions: `Button` with stable `id`s; spacing comes from `min-width:16`,
  shrink via CSS. `compact=True` and `flat=True` are safe on 8.2.8.
- Sections: `Collapsible` — constructor children collapse; post-mounts land
  outside the body, so prebuild all children. `enter` on the title toggles.
- Chrome: `Header` (per-screen `TITLE`) and `Footer` (auto-shows bindings).
  `Footer(compact=True)` saves a row; `show_command_palette=False` hides
  the palette hint.
- Lists: `OptionList` and `SelectionList` both accept `compact=True`;
  `OptionList` is the single-choice palette base, `SelectionList` is for
  multi-select checklists.
- Source trail: `Tree` with repo/commit/file/PR nodes in `TreeNode.data`;
  keep the preview in a `Static` (inside `#source-preview`) and actions on
  the screen. Diff text is plain Rich markup in that Static — no second
  widget tree and no syntax-highlight widget. Do not mount a second widget
  tree just for details.
- Detail page: plain `Screen`. Dialogs: `ModalScreen`.

## Version flags (8.2.8)

- `Input.compact`, `Checkbox.compact`, `Button.compact` safe (3.2.0+).
- `Button.flat` safe (6.1.0+). `Tabs.get_tab` present (8.0+).
- `Static.content` / `Label(content=)` — the old `renderable` names broke
  in 6.x; never use them.
- TextArea `tab_behavior="focus"` (default) lets Tab leave; `"indent"`
  traps Tab and releases on Esc.
