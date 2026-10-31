# Widgets

**Textual:** 8.2.8
**Official:** https://textual.textualize.io/guide/widgets/

Build custom widgets: compose, render, styles, messages, and lifecycle.

## What it covers

- Widget subclass
- compose
- render
- DEFAULT_CSS
- refresh

## Core concepts

Use this guide for the workflow, then open the category references for exact
APIs. The guide explains how the pieces fit; the reference files carry the
pinned signatures, styles, and event details.

## APIs

- Widget
- Static
- Message

## Related references

Guides:

- [events](events.md)
- [css](css.md)

Reference files:

- [widgets](../../textual-widgets/SKILL.md)
- [events](../../textual-events/SKILL.md)

## Example

```python
class Badge(Static):
    DEFAULT_CSS = "Badge { padding: 0 1; }"
```

## Pitfalls

- Call refresh after render-state changes; do not rebuild the tree for a style change.
