---
name: tui-input
description: Keyboard, focus, and dirty-state rules for the lazyplan TUI. Use when adding keybindings, changing focus behavior, editing save/close flows, or touching BINDINGS, Footer, or the editor dirty check.
license: MIT
compatibility: opencode, claude-code, codex, gemini-cli, cursor
---
# tui-input — keys, focus, dirty state (Textual 8.2.8 pinned)

Distilled from https://textual.textualize.io/guide/input/ and
https://textual.textualize.io/guide/actions/.

## Rules

- Lookup order: focused widget → up the DOM → App. Saves/quits that must
  work inside inputs use `priority=True`. Never mutate `BINDINGS` at
  runtime — use `check_action()` + `refresh_bindings()`.
- `Footer` auto-shows bindings; `show=False` hides. Terminals swallow many
  combos — stick to letters, F-keys, space, arrows, ctrl/shift; probe with
  `textual keys`. `Input` already binds ~20 keys; don't reuse them blindly.
- Descriptions edit multi-line only while focused (`DescendantFocus`
  swaps Input → TextArea; `DescendantBlur` folds back). Full text lives in
  a synced map; collapsed Inputs hold the first line with the stored tail.
- Dirty state is a baseline snapshot comparison (`_snapshot` /
  `_is_dirty`), never event flags — mount-time `Changed` messages make
  clean screens arrive dirty. Esc compares and prompts only on real edits.
