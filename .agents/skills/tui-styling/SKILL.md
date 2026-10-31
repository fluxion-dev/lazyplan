---
name: tui-styling
description: Styling rules for the lazyplan TUI — design.py as single source of truth, scoped CSS, and compact buttons. Use when touching APP_CSS, row grammar, status glyphs, help text, or any widget styling.
license: MIT
compatibility: opencode, claude-code, codex, gemini-cli, cursor
---
# tui-styling — tokens and CSS (Textual 8.2.8 pinned)

Reviewed 2026-10-24 against the current CSS, styles, themes, and design
guides. 8.2.8 is the latest PyPI release.

Distilled from https://textual.textualize.io/guide/CSS/ and
https://textual.textualize.io/guide/design/.

## Rules

- `design.py` is the single source of truth: if you add a view, command,
  or message, add it there first. Row grammar
  (`GLYPH KIND#id title`), status words, chips, empty states, and
  `HELP_TEXT` all live there; `lpui help` and the `?` overlay render the
  same text.
- App CSS always beats widget `DEFAULT_CSS`. Scope editor rules under
  `#editor`, dialog rules under `#dlg` — never style bare `Button`/`Input`
  globally (the tree and footer must stay untouched).
- State via classes (`add_class` / `set_class`, or `update_classes` for an
  atomic add/remove pair), never inline `styles.*` except dynamic values.
- Component sub-parts: `tree--cursor`, `input--cursor`,
  `text-area--gutter`, `toggle--button`. Theme vars `$primary`, `$panel`,
  `$foreground`, `$success`, `$error`; link colours use `$link-color`,
  `$link-color-hover`, and the other `link-*` theme variables.
- Compact buttons: `min-width: 0; width: auto; height: 3; padding: 0 1;`
  scoped to `#dlg`, `#help`, and `#detail-page`; height 1 clips the label
  in Textual 8.2.8. Short labels (`Save`, `Cancel`, `Create`, `Close`).
- Source CSS: `#source-page` is the frame, `#source-main` splits a
  `1fr/1fr` tree and preview, `#source-filter` is a hidden Input revealed by
  `/`. Keep the tree scroller and preview scroller independent.
- Diff previews use Rich markup only: `[green]+` / `[red]-`, dim line-number
  gutters, bold file headers, cyan hunk headers. Provenance lives in the row
  chips from `design.py`; never bake a glyph into a title.
