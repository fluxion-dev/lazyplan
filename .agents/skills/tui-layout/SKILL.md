---
name: tui-layout
description: Layout discipline for the lazyplan TUI — containers, scroll, and compact rows. Use when changing screen structure, scroll behavior, card layouts, or button rows in src/lazyplan/screens.py, tui.py, or design.py.
license: MIT
compatibility: opencode, claude-code, codex, gemini-cli, cursor
---
# tui-layout — containers and scroll (Textual 8.2.8 pinned)

Distilled from https://textual.textualize.io/guide/layout/ and
https://textual.textualize.io/how-to/work-with-containers/.

## Rules

- `Vertical` / `Horizontal` are `1fr` with overflow hidden — they never
  scroll. Scrolling needs `VerticalScroll` / `HorizontalScroll`, and inner
  content containers must be `height: auto` or the scroller sees no
  overflow (this exact bug hid editor content: `#cards { height: auto; }`).
- Tight action rows use `Horizontal` with compact button CSS; modals wrap
  button pairs in `Horizontal`.
- Collapsed `Collapsible` sections cost one row each — the default for
  long lists; only the focus chain opens.
- `Screen` stacks vertically by default. Dock chrome (`Header`/`Footer`);
  `1fr` shares whatever remains.
- `display: none` removes layout; `visibility: hidden` keeps space.

## Mount / scroll discipline

- `await container.mount(w)`, then `call_after_refresh` before any
  `scroll_to_widget` — scrolling pre-layout is a silent no-op.
- `await box.remove_children()` before remounting the same ids or
  `DuplicateIds` fires. Rebuilds drop focus and scroll — re-focus the
  anchor and re-scroll explicitly.
