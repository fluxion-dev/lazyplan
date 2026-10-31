# Command Palette

**Textual:** 8.2.8
**Official:** https://textual.textualize.io/guide/command_palette/

Provide commands, search, and hit handling for the palette.

## What it covers

- commands
- Provider
- Hit
- search
- system commands

## Core concepts

Use this guide for the workflow, then open the category references for exact
APIs. The guide explains how the pieces fit; the reference files carry the
pinned signatures, styles, and event details.

## APIs

- App.COMMANDS
- Provider
- CommandPalette

## Related references

Guides:

- [actions](actions.md)
- [input](input.md)

Reference files:

- [widgets](../../textual-widgets/SKILL.md)
- [events](../../textual-events/SKILL.md)

## Example

```python
COMMANDS = {"save": lambda: self.save()}
```

## Pitfalls

- Command ids must be stable; palette selection is fuzzy.
