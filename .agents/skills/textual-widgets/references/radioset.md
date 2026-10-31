# RadioSet

**Textual:** 8.2.8 · **Import:** `from textual.widgets import RadioSet`
**Official:** https://textual.textualize.io/widgets/radioset/

A mutually exclusive group of RadioButton children.

## Constructor

```python
RadioSet(*buttons: 'str | RadioButton', name: 'str | None' = None, id: 'str | None' = None, classes: 'str | None' = None, disabled: 'bool' = False, tooltip: 'RenderableType | None' = None, compact: 'bool' = False) -> 'None'
```

## Key properties and methods

- pressed_index
- pressed_button

## Messages

- Changed — emitted when the selected button changes.

## CSS

- RadioSet — group.

## Example

```python
yield RadioSet(RadioButton("Fast", id="fast"), RadioButton("Safe", id="safe"))
```

## Pitfalls

- Use pressed_index for the current choice; initial selection is silent.

## See also

- [Widgets index](../SKILL.md)
- `help(textual.widgets.RadioSet)`
