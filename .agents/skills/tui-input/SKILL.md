---
name: tui-input
description: Keyboard, focus, and dirty-state rules for the lazyplan TUI. Use when adding keybindings, changing focus behavior, editing save/close flows, or touching BINDINGS or form dirty checks.
license: MIT
compatibility: opencode, claude-code, codex, gemini-cli, cursor
---
# tui-input — keys, focus, dirty state (Textual 8.2.8 pinned)

Reviewed 2026-10-24 against the current input/actions guides. 8.2.8 is the
latest PyPI release.

Distilled from https://textual.textualize.io/guide/input/ and
https://textual.textualize.io/guide/actions/.

## Rules

- Lookup order: focused widget → up the DOM → App. Saves/quits that must
  work inside inputs use `priority=True`. Never mutate `BINDINGS` at
  runtime — use `check_action()` + `refresh_bindings()`.
- 8.2.7+ reports modifier keys more reliably on Kitty-protocol terminals,
  including alt/option and cmd combinations. Still probe with
  `textual keys` and keep a plain-letter fallback for important actions.
- `Footer` auto-shows bindings; `show=False` hides and `compact=True`
  reclaims a chrome row without hiding them. Terminals swallow many
  combos — stick to letters, F-keys, space, arrows, ctrl/shift. `Input`
  already binds ~20 keys; don't reuse them blindly.
- Descriptions edit multi-line only while focused (`DescendantFocus`
  swaps Input → TextArea; `DescendantBlur` folds back). Full text lives in
  a synced map; collapsed Inputs hold the first line with the stored tail.
- Dirty state is a baseline snapshot comparison (`_snapshot` /
  `_is_dirty`), never event flags — mount-time `Changed` messages make
  clean screens arrive dirty. Esc compares and prompts only on real edits.
- Source screen keys: `g` opens, `j/k`/arrows navigate, `o` opens, `y`
  copies, `/` filters, `r` refreshes, `esc` returns. Keep these screen-level
  bindings; do not bind them on the inner Tree except navigation.
