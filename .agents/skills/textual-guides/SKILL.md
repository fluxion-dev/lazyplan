---
name: textual-guides
description: Every Textual 8.2.8 guide: the problem it solves, core concepts, APIs, links to the reference files it uses, examples, and pitfalls.
license: MIT
compatibility: opencode, claude-code, codex, gemini-cli, cursor
---
# Textual guides — Textual 8.2.8

Read the matching reference before writing or changing this part of a Textual
app. Every entry links the official page and the pinned API.

## Rules

- Pin all advice to Textual 8.2.8; check the installed version when a symbol is missing.
- Prefer composition and classes over inline styles and deep inheritance.
- Never copy long passages from the official docs; summarize and link.
- After a Textual upgrade, run `python3 tools/gen_textual_skills.py --check`.

## Index

| Item | Id |
| --- | --- |
| [Devtools](references/devtools.md) | `devtools` |
| [App Basics](references/app.md) | `app` |
| [Styles](references/styles.md) | `styles` |
| [Textual CSS](references/css.md) | `css` |
| [DOM Queries](references/queries.md) | `queries` |
| [Layout](references/layout.md) | `layout` |
| [Events and Messages](references/events.md) | `events` |
| [Input](references/input.md) | `input` |
| [Actions](references/actions.md) | `actions` |
| [Reactivity](references/reactivity.md) | `reactivity` |
| [Themes](references/design.md) | `design` |
| [Widgets](references/widgets.md) | `widgets` |
| [Content](references/content.md) | `content` |
| [Animation](references/animation.md) | `animation` |
| [Screens](references/screens.md) | `screens` |
| [Workers](references/workers.md) | `workers` |
| [Command Palette](references/command_palette.md) | `command_palette` |
| [Testing](references/testing.md) | `testing` |

## See also

- [Textual router](../textual/SKILL.md)
- [Coverage manifest](../textual/references/_manifest.json)
