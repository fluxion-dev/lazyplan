# align

**Textual:** 8.2.8
**Official:** https://textual.textualize.io/styles/align/

Shorthand for horizontal and vertical alignment of children.

## Values

`left|center|right + top|middle|bottom, or a pair`

## Default and inheritance

Default: left top. Textual resolves the final value from the widget, its
classes, the app CSS, and the active theme. Use `styles.get_rule()` or the
devtools CSS inspector when the cascade is unclear.

## Applies to

containers and widgets with children.

## Example

```css
align: inherit;
```

## Related

- `align-horizontal, align-vertical`

## See also

- [Styles index](../SKILL.md)
- [CSS types index](../../textual-css-types/SKILL.md)
