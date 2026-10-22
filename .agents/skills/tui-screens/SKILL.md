---
name: tui-screens
description: Screen and modality rules for the lazyplan TUI — detail pages, modals, stack guards, and dismiss payloads. Use when adding screens, changing open/close flows, or touching push_screen/dismiss paths in tui.py or screens.py.
license: MIT
compatibility: opencode, claude-code, codex, gemini-cli, cursor
---
# tui-screens — modality (Textual 8.2.8 pinned)

Distilled from https://textual.textualize.io/guide/screens/.

## Rules

- Detail page = plain `Screen` (`DetailScreen`); dialogs =
  `ModalScreen` subclasses of `_Form` (Esc cancels, dirty drafts confirm).
- Only the top screen receives input. Every opener checks
  `len(self.screen_stack) > 1` and bails when a modal owns the keys.
- Return data via `dismiss(result)` + push callbacks; `None` means cancel
  and every callback treats it as such.
- Detail actions resolve the selection (`dkind`/`doid`); with no
  selection, the palette disables the command with a reason.
- Structural mutations (add/delete/status) rebuild and re-snapshot; new
  ids come from `services.create_*` with `actor="tui"`.
- Patch writes use `Store.update_*` (`None` keeps, `""` clears priority)
  plus `set_criteria`; `ValueError` surfaces via `notify(msg_error(...))`.
