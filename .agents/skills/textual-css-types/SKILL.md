---
name: textual-css-types
description: Every Textual 8.2.8 CSS type: grammar, examples, and which styles consume it. Use when a style value is rejected or its syntax is unclear.
license: MIT
compatibility: opencode, claude-code, codex, gemini-cli, cursor
---
# Textual CSS types — Textual 8.2.8

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
| [<border>](references/border.md) | `border` |
| [<color>](references/color.md) | `color` |
| [<hatch>](references/hatch.md) | `hatch` |
| [<horizontal>](references/horizontal.md) | `horizontal` |
| [<integer>](references/integer.md) | `integer` |
| [<keyline>](references/keyline.md) | `keyline` |
| [<name>](references/name.md) | `name` |
| [<number>](references/number.md) | `number` |
| [<overflow>](references/overflow.md) | `overflow` |
| [<pointer>](references/pointer.md) | `pointer` |
| [<position>](references/position.md) | `position` |
| [<percentage>](references/percentage.md) | `percentage` |
| [<scalar>](references/scalar.md) | `scalar` |
| [<text-align>](references/text_align.md) | `text_align` |
| [<text-style>](references/text_style.md) | `text_style` |
| [<vertical>](references/vertical.md) | `vertical` |

## See also

- [Textual router](../textual/SKILL.md)
- [Coverage manifest](../textual/references/_manifest.json)
