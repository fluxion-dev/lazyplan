---
name: tui-screens
description: Screen and modality rules for the lazyplan TUI — detail pages, modals, stack guards, and dismiss payloads. Use when adding screens, changing open/close flows, or touching push_screen/dismiss paths in tui.py or screens.py.
license: MIT
compatibility: opencode, claude-code, codex, gemini-cli, cursor
---
# tui-screens — modality (Textual 8.2.8 pinned)

Reviewed 2026-10-24 against the current screens guide. 8.2.8 is the latest
PyPI release.

Distilled from https://textual.textualize.io/guide/screens/.

## Rules

- Detail page = plain `Screen` (`DetailScreen`); dialogs =
  `ModalScreen` subclasses of `_Form` (Esc cancels, dirty drafts confirm).
  Type results as `ModalScreen[T]` so `dismiss(value)` and callbacks agree.
- Only the top screen receives input. Every opener checks
  `len(self.screen_stack) > 1` and bails when a modal owns the keys.
- Return data via `dismiss(result)` + push callbacks; `None` means cancel
  and every callback treats it as such. `App.push_screen_wait()` exists but
  only works from a worker; prefer callbacks unless a flow truly needs to
  await a screen.
- Detail actions resolve the selection (`dkind`/`doid`); with no
  selection, the palette disables the command with a reason.
- `SourceScreen` is a plain `Screen` opened by `g` from the main tree or
  detail. It owns a `Tree` (`repo -> commit -> file`, PRs grouped by repo), a
  Static preview, and a Footer; `escape` pops back. Open/copy are explicit
  actions and never call the network.
- Structural mutations (add/delete/status) rebuild and re-snapshot; new
  ids come from `services.create_*` with `actor="tui"`.
- Patch writes use `Store.update_*` (`None` keeps, `""` clears priority)
  plus `set_criteria`; `ValueError` surfaces via `notify(msg_error(...))`.
