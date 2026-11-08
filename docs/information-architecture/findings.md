# Information architecture findings

Ranked from the [inventory](inventory.md). Every finding cites the inventory
section that proves it and names the milestone that will resolve it. The
inventory is generated; this file is reviewed by hand.

| ID | Severity | Finding | Evidence | Target |
| --- | --- | --- | --- | --- |
| IA-001 | High | Fourteen keys run different actions on different screens, so muscle memory does not transfer between the tree and detail/source screens. | `inventory.md` → TUI key conflicts (`a`, `d`, `e`, `q`, `s`, `x`, and others). | M452 |
| IA-002 | High | `q` quits the app from the tree but adds a question from detail; the same key is destructive in one context and additive in another. | `inventory.md` → TUI key conflicts, key `q` (`app.py` → `quit`, `screens/detail.py` → `add_question`). | M452 |
| IA-003 | High | Criteria, evidence, questions, references, claims, touch-points, sessions, comments, notes, repos, commits, files, PRs, feed rows, and override events have no selectable hub; most are read-only text or CLI-only. | `inventory.md` → TUI screens and CLI commands vs MCP tools; the palette has no hub commands. | M453–M455 |
| IA-004 | High | There is no canonical action registry, so palette IDs, CLI verbs, and MCP tool names use three independent vocabularies. | `inventory.md` → Palette commands, CLI commands, MCP tools; counts 50 / 61 / 34 with no shared ID column. | M451 |
| IA-005 | Medium | Legacy CLI aliases are inventoried but not marked as deprecated, so no removal target exists. | `inventory.md` → CLI commands (flat verbs such as `add-plan`, `update`, `status`). | M456 |
| IA-006 | Medium | Setup steps, hook events, and documentation headings are inventoried but not mapped into the action taxonomy. | `inventory.md` → Setup steps, Hook events, Documentation headings. | M456 |
| IA-007 | Medium | The palette exposes actions with no parity decision against CLI or MCP; there is no exception list. | `inventory.md` → Palette commands vs MCP tools. | M456 |
| IA-008 | Low | Retained docs, man pages, site, and skills use separate heading taxonomies. | `inventory.md` → Documentation headings. | M456 |
| IA-009 | Closed | Stale paths and stale key claims from earlier releases. | `inventory.md` → Stale claims: zero found after P137. | Closed |
