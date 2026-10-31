# background

**Textual:** 8.2.8
**Official:** https://textual.textualize.io/styles/background/

Background colour or gradient behind the widget.

## Values

`colour, gradient, or transparent`

## Default and inheritance

Default: theme surface. Textual resolves the final value from the widget, its
classes, the app CSS, and the active theme. Use `styles.get_rule()` or the
devtools CSS inspector when the cascade is unclear.

## Applies to

all widgets.

## Example

```css
background: $primary;
```

## Related

- `background-tint, color`

## See also

- [Styles index](../SKILL.md)
- [CSS types index](../../textual-css-types/SKILL.md)
