# Layout

**Textual:** 8.2.8
**Official:** https://textual.textualize.io/guide/layout/

Vertical, horizontal, and grid layouts with dock, alignment, and scroll containers.

## What it covers

- layout
- width/height
- fr units
- dock
- grid
- overflow

## Core concepts

Use this guide for the workflow, then open the category references for exact
APIs. The guide explains how the pieces fit; the reference files carry the
pinned signatures, styles, and event details.

## APIs

- Container
- Horizontal
- Vertical
- Grid
- ScrollableContainer

## Related references

Guides:

- [styles](styles.md)
- [widgets](widgets.md)

Reference files:

- [layout](../../textual-layout/SKILL.md)
- [styles](../../textual-styles/SKILL.md)

## Example

```python
with Horizontal():
    yield Tree("plans")
    yield Static("preview")
```

## Pitfalls

- Nested 1fr containers need a height; auto-height does not fill.
