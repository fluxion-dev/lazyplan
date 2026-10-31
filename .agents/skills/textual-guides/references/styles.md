# Styles

**Textual:** 8.2.8
**Official:** https://textual.textualize.io/guide/styles/

The styles object, inline styles, reactive updates, and style inheritance.

## What it covers

- styles.*
- set_styles
- classes vs inline
- theme variables

## Core concepts

Use this guide for the workflow, then open the category references for exact
APIs. The guide explains how the pieces fit; the reference files carry the
pinned signatures, styles, and event details.

## APIs

- Widget.styles
- Widget.add_class
- Widget.set_class

## Related references

Guides:

- [css](css.md)
- [design](design.md)

Reference files:

- [styles](../../textual-styles/SKILL.md)
- [css-types](../../textual-css-types/SKILL.md)

## Example

```python
widget.styles.background = "$panel"
```

## Pitfalls

- Prefer classes for static styling; inline styles for dynamic values.
