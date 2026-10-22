---
name: tui-widgets
description: Widget catalog for the lazyplan TUI — which widget to use for what, with pinned-version flags. Use when adding or changing any Tree, Input, TextArea, Checkbox, Button, Collapsible, Header, Footer, Screen, or modal in src/lazyplan/tui.py or screens.py.
license: MIT
compatibility: opencode, claude-code, codex, gemini-cli, cursor
---
# tui-widgets — widget catalog (Textual 8.2.8 pinned)

Distilled from https://textual.textualize.io/widget_gallery/ plus
`docs/textual-research.md`. Rules first, links second.

## Choices

- Hierarchy display: `Tree` with model ids in `TreeNode.data`.
  `NodeHighlighted` drives previews, `NodeSelected` (enter) opens editors.
  Never rebind `space` (toggle), `shift+space` (expand all), or arrows.
- Single-line entry: `Input`. Multi-line: `TextArea` — but mounting many
  TextAreas is heavy, so lists use one-line Inputs with focus-expand.
- Toggles: `Checkbox` (`enter`/`space` toggles, initial value is silent).
- Actions: `Button` with stable `id`s; spacing comes from `min-width:16`,
  shrink via CSS. `compact=True` and `flat=True` are safe on 8.2.8.
- Sections: `Collapsible` — constructor children collapse; post-mounts land
  outside the body, so prebuild all children. `enter` on the title toggles.
- Chrome: `Header` (per-screen `TITLE`) and `Footer` (auto-shows bindings).
- Detail page: plain `Screen`. Dialogs: `ModalScreen`.

## Version flags (8.2.8)

- `Input.compact`, `Checkbox.compact`, `Button.compact` safe (3.2.0+).
- `Button.flat` safe (6.1.0+). `Tabs.get_tab` present (8.0+).
- `Static.content` / `Label(content=)` — the old `renderable` names broke
  in 6.x; never use them.
- TextArea `tab_behavior="focus"` (default) lets Tab leave; `"indent"`
  traps Tab and releases on Esc.
