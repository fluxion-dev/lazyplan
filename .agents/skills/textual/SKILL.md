---
name: textual
description: Router for the complete Textual 8.2.8 skill suite. Use for any Textual widget, style, event, CSS type, container, screen, or guide question; choose the category skill and read the matching reference.
license: MIT
compatibility: opencode, claude-code, codex, gemini-cli, cursor
---
# Textual 8.2.8 skill suite

This suite covers the Textual reference and guide at 8.2.8. Start here, then
open the category skill and the one reference file you need.

## Choose a skill

| Skill | Use for |
| --- | --- |
| [`textual-widgets`](../textual-widgets/SKILL.md) | Textual widgets |
| [`textual-styles`](../textual-styles/SKILL.md) | Textual styles |
| [`textual-events`](../textual-events/SKILL.md) | Textual events |
| [`textual-css-types`](../textual-css-types/SKILL.md) | Textual CSS types |
| [`textual-layout`](../textual-layout/SKILL.md) | Textual layout, containers, and screens |
| [`textual-guides`](../textual-guides/SKILL.md) | Textual guides |

## Routing rules

- A concrete class, control, or display element → `textual-widgets`.
- A CSS property, value, or cascade question → `textual-styles`; follow a value
  question to `textual-css-types`.
- A handler, key, mouse, focus, lifecycle, or custom message → `textual-events`.
- A container, screen, modal, sizing, docking, grid, or scroll layout → `textual-layout`.
- A workflow or concept ("how do I test this?", "how do screens work?") →
  `textual-guides`, then the linked category reference.

## Coverage

The manifest at `references/_manifest.json` is the source of truth for the
suite. It records the pinned version, every item, its category, its reference
file, and the official URL. `python3 tools/gen_textual_skills.py --check`
fails on a missing file, missing heading, duplicate id, or version drift.

## Official sources

- Reference: https://textual.textualize.io/reference/
- Guide: https://textual.textualize.io/guide/
- API: https://textual.textualize.io/api/

The suite is a distilled index, not a substitute for the official pages. Read
the linked page when behavior or version support is uncertain.
