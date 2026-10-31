# layout

**Textual:** 8.2.8
**Official:** https://textual.textualize.io/styles/layout/

Selects the child layout algorithm.

## Values

`vertical|horizontal|grid`

## Default and inheritance

Default: vertical. Textual resolves the final value from the widget, its
classes, the app CSS, and the active theme. Use `styles.get_rule()` or the
devtools CSS inspector when the cascade is unclear.

## Applies to

containers.

## Example

```css
layout: inherit;
```

## Related

- `grid-*, dock, align`

## See also

- [Styles index](../SKILL.md)
- [CSS types index](../../textual-css-types/SKILL.md)
