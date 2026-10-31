# Content

**Textual:** 8.2.8
**Official:** https://textual.textualize.io/guide/content/

Rich renderables, markup, Text, and content sizing.

## What it covers

- Rich renderables
- Text
- markup
- Content
- measure

## Core concepts

Use this guide for the workflow, then open the category references for exact
APIs. The guide explains how the pieces fit; the reference files carry the
pinned signatures, styles, and event details.

## APIs

- Static
- Label
- RichLog

## Related references

Guides:

- [widgets](widgets.md)
- [styles](styles.md)

Reference files:

- [widgets](../../textual-widgets/SKILL.md)
- [styles](../../textual-styles/SKILL.md)

## Example

```python
yield Static("[bold]ready[/]", markup=True)
```

## Pitfalls

- Escape user text before embedding it in markup.
