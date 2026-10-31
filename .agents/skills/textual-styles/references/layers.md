# layers

**Textual:** 8.2.8
**Official:** https://textual.textualize.io/styles/layers/

Declares the layer order for a container.

## Values

`space-separated layer names`

## Default and inheritance

Default: default. Textual resolves the final value from the widget, its
classes, the app CSS, and the active theme. Use `styles.get_rule()` or the
devtools CSS inspector when the cascade is unclear.

## Applies to

containers.

## Example

```css
layers: base overlay;
```

## Related

- `layer`

## See also

- [Styles index](../SKILL.md)
- [CSS types index](../../textual-css-types/SKILL.md)
