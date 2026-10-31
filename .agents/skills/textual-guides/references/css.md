# Textual CSS

**Textual:** 8.2.8
**Official:** https://textual.textualize.io/guide/CSS/

The CSS language: selectors, specificity, pseudo-classes, nesting, and app CSS.

## What it covers

- type/id/class selectors
- pseudo-classes
- :focus
- DEFAULT_CSS
- CSS variables

## Core concepts

Use this guide for the workflow, then open the category references for exact
APIs. The guide explains how the pieces fit; the reference files carry the
pinned signatures, styles, and event details.

## APIs

- App.CSS
- Widget.DEFAULT_CSS
- Widget.styles

## Related references

Guides:

- [styles](styles.md)
- [layout](layout.md)

Reference files:

- [styles](../../textual-styles/SKILL.md)
- [css-types](../../textual-css-types/SKILL.md)
- [layout](../../textual-layout/SKILL.md)

## Example

```python
Button.primary { background: $accent; }
```

## Pitfalls

- App CSS beats DEFAULT_CSS; scope rules instead of styling bare types.
