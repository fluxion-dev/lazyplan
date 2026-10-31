# width

**Textual:** 8.2.8
**Official:** https://textual.textualize.io/styles/width/

Widget width as cells, fraction, or auto.

## Values

`scalar: cells, %, fr, auto`

## Default and inheritance

Default: auto. Textual resolves the final value from the widget, its
classes, the app CSS, and the active theme. Use `styles.get_rule()` or the
devtools CSS inspector when the cascade is unclear.

## Applies to

all widgets.

## Example

```css
width: 1fr;
```

## Related

- `min-width, max-width`

## See also

- [Styles index](../SKILL.md)
- [CSS types index](../../textual-css-types/SKILL.md)
