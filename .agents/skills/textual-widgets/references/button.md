# Button

**Textual:** 8.2.8 · **Import:** `from textual.widgets import Button`
**Official:** https://textual.textualize.io/widgets/button/

A pressable action with a label, optional icon, and pressed message.

## Constructor

```python
Button(label: 'ContentText | None' = None, variant: 'ButtonVariant' = 'default', *, name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False, tooltip: 'RenderableType | None' = None, action: 'str | None' = None, compact: 'bool' = False, flat: 'bool' = False)
```

## Key properties and methods

- label
- variant
- compact
- flat
- disabled

## Messages

- Pressed — emitted when activated by click, Enter, or Space.

## CSS

- Button — the outer widget.
- button--label, button--icon — inner parts.

## Example

```python
yield Button("Save", id="save", variant="primary")
```

## Pitfalls

- Mount buttons with stable ids; do not style bare Button globally.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.Button)`
