# Information architecture findings

Ranked from the [inventory](inventory.md). Every finding cites the inventory
section that proves it. The inventory is generated; this file is reviewed by
hand. The registry, keymap, hub, and parity work landed with releases v0.36
through v0.44; every finding below is closed and kept as the audit trail.

| ID | Severity | Finding | Evidence | Target |
| --- | --- | --- | --- | --- |
| IA-001 | Closed | Fourteen keys ran different actions on different screens, so muscle memory did not transfer between the tree and detail/source screens. | `inventory.md` → TUI key conflicts (`a`, `d`, `e`, `q`, `s`, `x`, and others). | Closed |
| IA-002 | Closed | `q` quit the app from the tree but added a question from detail; the same key was destructive in one context and additive in another. | `inventory.md` → TUI key conflicts, key `q`. | Closed |
| IA-003 | Closed | Criteria, evidence, questions, references, claims, touch-points, sessions, comments, notes, repos, commits, files, PRs, and feed rows had no selectable hub. | `inventory.md` → TUI screens and CLI commands vs MCP tools. | Closed |
| IA-004 | Closed | There was no canonical action registry, so palette IDs, CLI verbs, and MCP tool names used three independent vocabularies. | `inventory.md` → Palette commands, CLI commands, MCP tools with no shared ID column. | Closed |
| IA-005 | Closed | Legacy CLI aliases were inventoried but not marked as deprecated, so no removal target existed. | `inventory.md` → CLI commands (flat verbs such as `add-plan`, `update`, `status`). | Closed |
| IA-006 | Closed | Setup steps, hook events, and documentation headings were inventoried but not mapped into the action taxonomy. | `inventory.md` → Setup steps, Hook events, Documentation headings. | Closed |
| IA-007 | Closed | The palette exposed actions with no parity decision against CLI or MCP; there was no exception list. | `inventory.md` → Palette commands vs MCP tools. | Closed |
| IA-008 | Closed | Retained docs, man pages, site, and skills used separate heading taxonomies. | `inventory.md` → Documentation headings. | Closed |
| IA-009 | Closed | Stale paths and stale key claims from earlier releases. | `inventory.md` → Stale claims: zero found after P137. | Closed |
