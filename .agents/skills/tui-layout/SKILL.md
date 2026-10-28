---
name: tui-layout
description: Layout discipline for the lazyplan TUI — containers, scroll, and compact rows. Use when changing screen structure, scroll behavior, card layouts, or button rows in src/lazyplan/tui/screens/, tui/app.py, or design.py.
license: MIT
compatibility: opencode, claude-code, codex, gemini-cli, cursor
---
# tui-layout — containers and scroll (Textual 8.2.8 pinned)

Reviewed 2026-10-24 against the current layout guide and container how-to.
8.2.8 is the latest PyPI release.

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
  `1fr` shares whatever remains. `Footer(compact=True)` and
  `Header(show_clock=False)` reclaim chrome rows without losing bindings.
- `display: none` removes layout; `visibility: hidden` keeps space.
- Source screen: `#source-main` is a `Horizontal` with two
  `VerticalScroll` children (tree and preview); the filter Input sits above
  it and is hidden until `/`. The preview scroller owns diff overflow and
  resets to the top (`scroll_home`) on every selection change.

## Mount / scroll discipline

- `await container.mount(w)`, then `call_after_refresh` before any
  `scroll_to_widget` — scrolling pre-layout is a silent no-op.
- `await box.remove_children()` before remounting the same ids or
  `DuplicateIds` fires. Rebuilds drop focus and scroll — re-focus the
  anchor and re-scroll explicitly.
