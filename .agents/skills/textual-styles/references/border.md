# border

**Textual:** 8.2.8
**Official:** https://textual.textualize.io/styles/border/

Shorthand for width, style, and colour on all four edges.

## Values

`edge, style, colour; per-edge variants exist`

## Default and inheritance

Default: none. Textual resolves the final value from the widget, its
classes, the app CSS, and the active theme. Use `styles.get_rule()` or the
devtools CSS inspector when the cascade is unclear.

## Applies to

all widgets.

## Example

```css
border: solid $primary;
```

## Related

- `outline, border-title-*`

## See also

- [Styles index](../SKILL.md)
- [CSS types index](../../textual-css-types/SKILL.md)
