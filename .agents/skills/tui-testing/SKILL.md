---
name: tui-testing
description: Headless TUI testing for lazyplan — pilot patterns, state asserts, and gates. Use when testing any screen, widget flow, or keybinding, or when verifying UI changes.
license: MIT
compatibility: opencode, claude-code, codex, gemini-cli, cursor
---
# tui-testing — pilot patterns (Textual 8.2.8 pinned)

Distilled from https://textual.textualize.io/guide/testing/ and
https://textual.textualize.io/api/pilot/.

## Rules

- Harness: `async with app.run_test(size=(w, h)) as pilot:` (explicit
  viewport per test); `await pilot.pause()` to drain the queue before
  every assert. Clicks on covered or out-of-view widgets fail by design —
  prefer `.press()` / direct handler calls plus state asserts.
- Assert on state, not visuals: `Store` reads, widget values, screen
  stack depth and type, `scroll_y`. Existing patterns live in
  `tests/test_screens_esc.py` (esc discards, dirty-prompt flow).
- TUI tests skip on stdlib-only interpreters (`_TEXTUAL_OK` guard).
- Gates per `tools/check.sh`: ruff check, ruff format, mypy strict,
  vulture (+ `tools/vulture_allowlist.py` for framework-dispatched names),
  xenon max C, `gen-man.py --check`, `unittest discover` on both
  interpreters. Framework-dispatched handlers
  (`on_*`, `action_*`) go in the allowlist by name.
