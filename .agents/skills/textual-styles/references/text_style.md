# text-style

**Textual:** 8.2.8
**Official:** https://textual.textualize.io/styles/text_style/

Text decoration and emphasis.

## Values

`bold|italic|underline|reverse|strike|none, combinable`

## Default and inheritance

Default: none. Textual resolves the final value from the widget, its
classes, the app CSS, and the active theme. Use `styles.get_rule()` or the
devtools CSS inspector when the cascade is unclear.

## Applies to

all widgets with text.

## Example

```css
text-style: inherit;
```

## Related

- `link-style`

## See also

- [Styles index](../SKILL.md)
- [CSS types index](../../textual-css-types/SKILL.md)
