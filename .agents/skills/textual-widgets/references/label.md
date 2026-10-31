# Label

**Textual:** 8.2.8 · **Import:** `from textual.widgets import Label`
**Official:** https://textual.textualize.io/widgets/label/

A lightweight text widget for short labels and hints.

## Constructor

```python
Label(content: 'VisualType' = '', *, variant: 'LabelVariant | None' = None, expand: 'bool' = False, shrink: 'bool' = False, markup: 'bool' = True, name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False) -> 'None'
```

## Key properties and methods

- content
- markup
- variant

## Messages

- None.

## CSS

- Label — text block.

## Example

```python
yield Label("Status", variant="primary")
```

## Pitfalls

- Use Static for Rich renderables; Label is for text.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.Label)`
