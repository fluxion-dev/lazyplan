---
name: textual-layout
description: Textual 8.2.8 containers, screens, composition, sizing, docking, grids, scrolling, and lifecycle. Use when structuring a screen or debugging layout and navigation.
license: MIT
compatibility: opencode, claude-code, codex, gemini-cli, cursor
---
# Textual layout, containers, and screens — Textual 8.2.8

Read the matching reference before writing or changing this part of a Textual
app. Every entry links the official page and the pinned API.

## Rules

- Pin all advice to Textual 8.2.8; check the installed version when a symbol is missing.
- Prefer composition and classes over inline styles and deep inheritance.
- Never copy long passages from the official docs; summarize and link.
- After a Textual upgrade, run `python3 tools/gen_textual_skills.py --check`.

## Index

| Item | Id |
| --- | --- |
| [Container](references/container.md) | `container` |
| [Horizontal](references/horizontal.md) | `horizontal` |
| [Vertical](references/vertical.md) | `vertical` |
| [Grid](references/grid.md) | `grid` |
| [HorizontalScroll](references/horizontalscroll.md) | `horizontalscroll` |
| [VerticalScroll](references/verticalscroll.md) | `verticalscroll` |
| [Center](references/center.md) | `center` |
| [Middle](references/middle.md) | `middle` |
| [CenterMiddle](references/center_middle.md) | `center_middle` |
| [ScrollableContainer](references/scrollable_container.md) | `scrollable_container` |
| [ItemGrid](references/item_grid.md) | `item_grid` |
| [Screen](references/screen.md) | `screen` |
| [ModalScreen](references/modal_screen.md) | `modal_screen` |
| [Composition and lifecycle](references/composition.md) | `composition` |

## See also

- [Textual router](../textual/SKILL.md)
- [Coverage manifest](../textual/references/_manifest.json)
