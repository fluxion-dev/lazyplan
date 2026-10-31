# Themes

**Textual:** 8.2.8
**Official:** https://textual.textualize.io/guide/design/

Theme variables, light/dark themes, and design tokens.

## What it covers

- $primary
- $panel
- $text-muted
- theme variables
- design tokens

## Core concepts

Use this guide for the workflow, then open the category references for exact
APIs. The guide explains how the pieces fit; the reference files carry the
pinned signatures, styles, and event details.

## APIs

- App.theme
- App.register_theme
- Theme

## Related references

Guides:

- [css](css.md)
- [styles](styles.md)

Reference files:

- [styles](../../textual-styles/SKILL.md)
- [css-types](../../textual-css-types/SKILL.md)

## Example

```python
background: $panel;
color: $text;
```

## Pitfalls

- Theme variables are not arbitrary colours; use $name deliberately.
